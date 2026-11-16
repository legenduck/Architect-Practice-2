"""Validate cross-file links and derive materials from the two process records."""
from __future__ import annotations
import hashlib
import html
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def read_jsonl(path):
    return [json.loads(s) for s in path.read_text().splitlines() if s.strip()]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def state(root, state_id):
    p = root / 'states' / (state_id + '.json')
    require(p.is_file(), 'Missing state ' + state_id)
    data = json.loads(p.read_text())
    packed = json.dumps(data['files'], ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    require(state_id == 's-' + digest(packed.encode())[:20], 'State inventory hash mismatch')
    objects={}
    for sha in set(data['files'].values()):
        body=(root/'objects'/(sha+'.txt')).read_bytes()
        require(digest(body)==sha,'Object hash mismatch')
        objects[sha]=body
    for field, prefix in [('code_version', 'src/'), ('tests_version', 'tests/'), ('data_version', 'data/')]:
        h = hashlib.sha256()
        for name, sha in sorted(data['files'].items()):
            if name.startswith(prefix) and (prefix == 'data/' or name.endswith('.py')):
                blob = objects[sha]
                h.update(name.encode()); h.update(b'\0' + blob + b'\0')
        require(h.hexdigest() == data[field], 'State component hash mismatch')
    return data


def cost(usage, prices):
    return ((usage['input_tokens'] - usage['cached_input_tokens']) * prices['input_per_million'] + usage['cached_input_tokens'] * prices['cached_input_per_million'] + usage['output_tokens'] * prices['output_per_million']) / 1_000_000


def analyze(root=ROOT):
    manifest = json.loads((root / 'manifest.json').read_text())
    require(manifest['provenance']['kind'] == 'constructed', 'Dataset provenance must match its generation method')
    rows=[]; timelines={}; state_cache={}
    def checked(ref):
        if ref['state_id'] not in state_cache:
            state_cache[ref['state_id']] = state(root, ref['state_id'])
        value=state_cache[ref['state_id']]
        require(all(ref[k]==value[k] for k in ['code_version','tests_version','data_version']), 'State reference mismatch')
        return value

    for entry in manifest['runs']:
        code=read_jsonl(root/entry['codex']);harness=read_jsonl(root/entry['harness'])
        require(code and harness, 'Both records are required')
        require(code[0]['provenance']['kind']=='constructed' and harness[0]['provenance']['kind']=='constructed', 'Missing per-file provenance')
        ids=[r['event_id'] for r in code+harness]
        require(len(set(ids))==len(ids), 'Duplicate event ID')
        require(all(r['run_id']==entry['run_id'] for r in code+harness), 'Mixed run IDs')
        by_id={r['event_id']:r for r in code}
        starts={r['request_id']:r for r in code if r['type']=='request.started'}
        completions={r['request_id']:r for r in code if r['type']=='request.completed'}
        calls={r['call_id']:r for r in code if r['type']=='tool.call'}
        results={r['call_id']:r for r in code if r['type']=='tool.result'}
        model_spans={r['request_id']:r for r in harness if r['type']=='model.observed'}
        requests={r['request_id']:r for r in harness if r['type']=='request.completed'}
        tools=[r for r in harness if r['type']=='tool.observed']
        require(set(starts)==set(completions)==set(model_spans)==set(requests), 'Request links do not match')
        require(set(calls)==set(results)=={r['call_id'] for r in tools}, 'Tool links do not match')
        require(len(calls)==sum(r['type']=='tool.call' for r in code), 'Duplicate tool call ID')
        require(len(starts)==sum(r['type']=='request.started' for r in code), 'Duplicate request ID')
        totals={k:sum(r['usage'][k] for r in completions.values()) for k in ['input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens']}
        require(totals==code[-1]['usage'], 'Run usage is not the sum of requests')
        require(all(entry[k]==v for k,v in totals.items()),'Manifest usage differs from records')
        require(entry['llm_calls']==len(completions) and entry['tool_calls']==len(calls),'Manifest call counts differ from records')
        for r in completions.values():
            u=r['usage']
            require(all(type(v) is int and v>=0 for v in u.values()), 'Invalid token value')
            require(u['cached_input_tokens']<=u['input_tokens'], 'Cached input exceeds input')
            require(u['reasoning_output_tokens']<=u['output_tokens'], 'Reasoning output exceeds output')
            require(u['input_tokens']<272000, 'Rate-card context threshold exceeded')
        ordered=sorted(requests.values(),key=lambda x:x['start_ms'])
        cursor=0
        for r in ordered:
            request=r['request_id'];m=model_spans[request]
            require(r['start_ms']==cursor and r['end_ms']>r['start_ms'], 'Request timing gap or overlap')
            require(m['start_ms']==r['start_ms'] and m['end_ms']>=m['start_ms'], 'Invalid model span')
            require(by_id[m['start_event_id']]['request_id']==request, 'Model start event mismatch')
            require(by_id[m['response_event_id']]['request_id']==request, 'Model response event mismatch')
            require(by_id[r['usage_event_id']]['request_id']==request, 'Usage event mismatch')
            end=m['end_ms']
            for t in sorted([t for t in tools if t['request_id']==request],key=lambda x:x['start_ms']):
                require(t['start_ms']==end and t['end_ms']>=end, 'Tool span timing mismatch')
                end=t['end_ms']
                require(by_id[t['call_event_id']]==calls[t['call_id']], 'Tool call event mismatch')
                require(by_id[t['result_event_id']]==results[t['call_id']], 'Tool result event mismatch')
                require(calls[t['call_id']]['request_id']==results[t['call_id']]['request_id']==request, 'Tool linked to wrong request')
            require(end==r['end_ms'], 'Request duration does not match its components')
            cursor=r['end_ms']
        require(cursor==harness[-1]['at_ms'], 'Run elapsed time mismatch')
        require(abs(entry['elapsed_seconds']-cursor/1000)<1e-9,'Manifest time differs from records')
        previous=harness[0]['initial_state'];checked(previous)
        seen_docs=set();doc_lookups=0;doc_repeats=0
        prior_tests={};test_count=0;unchanged=0
        for t in tools:
            require(t['before']==previous, 'Broken before/after state chain')
            before=checked(t['before']);after=checked(t['after'])
            if t['operation'] in ('read','test','calculate'):
                require(t['before']==t['after'], 'Read-only operation changed state')
            for change in t.get('file_changes',[]):
                require(before['files'].get(change['path'])==change['before_sha256'], 'Incorrect file before hash')
                require(after['files'].get(change['path'])==change['after_sha256'], 'Incorrect file after hash')
            changed={n for n in set(before['files'])|set(after['files']) if before['files'].get(n)!=after['files'].get(n)}
            require(changed=={c['path'] for c in t.get('file_changes',[])},'Unreported file state change')
            expected_read=[]
            for source in t.get('resources',[]):
                require(before['files'][source['path']]==source['sha256'], 'Read target version mismatch')
                body=(root/'objects'/(source['sha256']+'.txt')).read_text()
                span=source['range']
                selected=body if span=='full' else ''.join(body.splitlines(True)[span[0]-1:span[1]])
                require(len(selected.encode())==source['bytes_returned'],'Read byte count mismatch')
                expected_read.append(f"--- {source['path']} ({span}) ---\n"+selected)
                if source['path'].startswith('docs/'):
                    doc_lookups+=1
                    identity=(source['path'],source['sha256'],json.dumps(source['range']))
                    doc_repeats+=identity in seen_docs;seen_docs.add(identity)
            if t['operation']=='read':
                require(results[t['call_id']]['stdout']=='\n'.join(expected_read),'Read result is not the referenced file range')
            if t['operation']=='test':
                test_count+=1
                key=(t['test_scope'],t['before']['code_version'],t['before']['tests_version'],t['before']['data_version'],t['environment_id'])
                if prior_tests.get(key) is True:unchanged+=1
                result=results[t['call_id']]; counts=t['test_result']
                require(counts['tests']==counts['passed']+counts['failed']+counts['skipped'], 'Invalid test count')
                prior_tests[key]=(result['exit_code']==0 and counts['failed']==counts['skipped']==0)
            previous=t['after']
        require(previous==harness[-1]['final_state'], 'Final state mismatch')
        final=checked(previous)
        grade=json.loads((root/entry['grading_evidence']).read_text())
        require(grade['run_id']==entry['source_run_id'] and grade['source_sha256']==final['code_version'], 'Final artifact is not the graded source artifact')
        require(grade['status']=='passed', 'Final artifact has not passed grading')
        require(grade['suites']['regression']['passed']==110 and grade['suites']['coupon']['passed']==12, 'Unexpected common grading criteria')
        fee_requests=[r for r in ordered if r['activity']=='금액 검증']
        fee_ids={r['request_id'] for r in fee_requests}
        fee_usage={k:sum(completions[r]['usage'][k] for r in fee_ids) for k in totals}
        check_ids=set()
        explanation_occurrences=0
        for r in code:
            if r['type']=='assistant.message' and r['request_id'] in fee_ids:
                check_ids.update(r.get('check_ids',[]))
                explanation_occurrences+=len(re.findall(r'\[C\d{2}\]',r['content']))
        expected_ids={c['id'] for c in json.loads((root/'calculation_cases.json').read_text())['cases']}
        require(check_ids==expected_ids,'Calculation check set differs across cases')
        fee_outputs=[]
        for t in tools:
            if t['operation']=='calculate':fee_outputs=json.loads(results[t['call_id']]['stdout'])
        if not fee_outputs:
            sha=final['files'].get('work/expected-fees.json')
            require(bool(sha),'Missing saved calculation result')
            fee_outputs=json.loads((root/'objects'/(sha+'.txt')).read_text())
        expected=[{'id':c['id'],'total':c['expected_total'],'coupon_status':c['expected_coupon_status']} for c in json.loads((root/'calculation_cases.json').read_text())['cases']]
        require(fee_outputs==expected,'Calculation results differ from checked examples')
        row={'scenario':entry['scenario'],'label':entry['label'],'run_id':entry['run_id'],'success':True,**totals,
             'first_input_tokens':next(iter(completions.values()))['usage']['input_tokens'],
             'llm_calls':len(completions),'tool_calls':len(calls),'test_runs':test_count,
             'same_state_passed_rechecks':unchanged,'document_lookups':doc_lookups,'same_document_range_lookups':doc_repeats,
             'elapsed_seconds':cursor/1000,'model_seconds':sum(m['end_ms']-m['start_ms'] for m in model_spans.values())/1000,
             'tool_seconds':sum(t['end_ms']-t['start_ms'] for t in tools)/1000,
             'estimated_cost':cost(totals,manifest['pricing']),
             'calculation_items':len(check_ids),'calculator_executions':sum(t['operation']=='calculate' for t in tools),
             'calculation_explanation_occurrences':explanation_occurrences,
             'calculation_input_tokens':fee_usage['input_tokens'],'calculation_output_tokens':fee_usage['output_tokens'],
             'calculation_seconds':sum(r['end_ms']-r['start_ms'] for r in fee_requests)/1000,
             'calculation_cost':cost(fee_usage,manifest['pricing'])}
        rows.append(row)
        timelines[entry['scenario']]=[]
        for r in ordered:
            request=r['request_id'];msgs=[e['content'] for e in code if e['type']=='assistant.message' and e['request_id']==request]
            matching=[t for t in tools if t['request_id']==request]
            timelines[entry['scenario']].append({'request_id':request,'activity':r['activity'],'start_ms':r['start_ms'],'end_ms':r['end_ms'],'message':'\n'.join(msgs),'usage':completions[request]['usage'],'tools':[{'call':calls[t['call_id']],'result':results[t['call_id']],'observation':t} for t in matching]})
    return manifest,rows,timelines


def text(value):return html.escape(str(value))


def table(headers, rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+text(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+text(x)+'</td>' for x in r)+'</tr>' for r in rows)+'</tbody></table></div>'


def render(manifest,rows,timelines):
    body='<h1>실습 2 작업 기록</h1><p>같은 쿠폰 과제를 수행하는 네 작업 방식입니다. 실행 기록과 수집 기록을 같은 호출 ID로 연결해 확인합니다.</p>'
    body+=table(['작업 방식','과제 결과','입력 토큰','출력 토큰','모델 호출','도구 호출','테스트','시간(초)','환산 비용(USD)'],[[r['label'],'통과',f"{r['input_tokens']:,}",f"{r['output_tokens']:,}",r['llm_calls'],r['tool_calls'],r['test_runs'],f"{r['elapsed_seconds']:.1f}",f"{r['estimated_cost']:.4f}"] for r in rows])
    body+='<p>각 사례의 작업 내역과 상태 변화를 확인한 뒤 평가 기준을 정합니다. <a href="materials.json">집계 재료</a>와 <a href="manifest.json">자료 메타데이터</a>를 함께 열 수 있습니다.</p>'
    for entry in manifest['runs']:
        name=entry['scenario'];body+='<details class="case"><summary>'+text(entry['label'])+'</summary>'
        body+='<p><a href="'+entry['codex']+'">codex.jsonl</a> / <a href="'+entry['harness']+'">harness.jsonl</a> / <a href="'+entry['grading_evidence']+'">최종 코드 채점 근거</a></p>'
        for step in timelines[name]:
            body+='<details class="step"><summary>'+text(step['request_id'])+' — '+text(step['activity'])+' <span>'+f"{step['start_ms']/1000:.1f}–{step['end_ms']/1000:.1f}초"+'</span></summary>'
            body+='<div class="message">'+text(step['message'])+'</div>'
            body+='<p class="usage">입력 '+f"{step['usage']['input_tokens']:,}"+' / 캐시 입력 '+f"{step['usage']['cached_input_tokens']:,}"+' / 출력 '+f"{step['usage']['output_tokens']:,}"+' 토큰</p>'
            for tool in step['tools']:
                call=tool['call'];observed=tool['observation'];result=tool['result']
                body+='<p><b>'+text(call['call_id'])+'</b> '+text(call['name'])+' / 종료 코드 '+text(result['exit_code'])+'</p>'
                body+=table(['상태','작업 전','작업 후'],[[label,observed['before'][key][:12],observed['after'][key][:12]] for key,label in [('code_version','코드'),('tests_version','테스트'),('data_version','입력 데이터')]])
                if observed.get('test_result'):
                    t=observed['test_result'];body+='<p>검증: '+text(t['passed'])+'/'+text(t['tests'])+' 통과 / 조건 ID '+text(observed['validation_key'][:12])+'</p>'
                if observed.get('resources'):
                    body+=table(['조회 대상','범위','버전'],[[x['path'],x['range'],x['sha256'][:12]] for x in observed['resources']])
                body+='<details><summary>명령과 반환값</summary><pre>'+text(json.dumps({'arguments':call['arguments'],'result':result},ensure_ascii=False,indent=2))+'</pre></details>'
            body+='</details>'
        body+='</details>'
    body+='<details><summary>자료 정보</summary><p>'+text(manifest['provenance']['generation_method'])+'</p><p>'+text(manifest['usage_model']['basis'])+'</p><p>'+text(manifest['time_model']['basis'])+'</p><p>'+text(manifest['provenance']['grading_scope'])+'</p></details>'
    css='body{font:18px/1.65 system-ui,sans-serif;color:#202329;max-width:1400px;margin:36px auto;padding:0 24px}h1{font-size:34px}table{border-collapse:collapse;width:100%;font-size:16px}th,td{text-align:left;padding:11px;border-bottom:1px solid #ddd;vertical-align:top}th{border-top:2px solid #222;white-space:nowrap}.scroll{overflow:auto}.case{margin:28px 0;border-top:2px solid #4169e1;padding-top:12px}.case>summary{font-size:24px;font-weight:700}.step{margin:16px 0 16px 14px;padding:12px;border-left:3px solid #c9d4fa}.step>summary{font-weight:600}.step span{color:#666;font-weight:400}.message{white-space:pre-wrap;margin-top:14px}.usage{color:#515e7a}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f5f7;padding:16px;font-size:14px}a{color:#4169e1}summary{cursor:pointer}@media(max-width:700px){body{padding:0 14px}.step{margin-left:0}h1{font-size:28px}}'
    return '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>실습 2 작업 기록</title><style>'+css+'</style><main>'+body+'</main></html>'


def main(root=ROOT):
    manifest,rows,timelines=analyze(root)
    definitions={
        'same_state_passed_rechecks':'같은 코드 버전, 테스트 버전, 입력 데이터, 환경과 검증 범위에서 앞선 실행이 통과한 뒤 다시 실행한 횟수. 필요성 판단은 포함하지 않음.',
        'same_document_range_lookups':'동일 문서 버전의 동일 범위를 앞서 조회한 뒤 다시 조회한 대상 횟수. 한 도구 호출에서 여러 자료를 조회하면 자료별로 집계.',
        'calculation_items':'동일한 금액 검증 입력 8개의 서로 다른 항목 수.',
        'calculation_explanation_occurrences':'금액 검증 메시지에 표시된 사례 ID의 등장 횟수. 숨겨진 내부 추론 횟수가 아님.',
        'model_seconds':'수집 기록에서 model.observed 구간의 시간 합계.',
        'tool_seconds':'수집 기록에서 tool.observed 구간의 시간 합계. 요청 전체 시간과 중복 합산하지 않음.',
    }
    (root/'materials.json').write_text(json.dumps({'dataset_id':manifest['dataset_id'],'definitions':definitions,'runs':rows},ensure_ascii=False,indent=2)+'\n')
    (root/'index.html').write_text(render(manifest,rows,timelines))
    for row in rows:
        print(json.dumps(row,ensure_ascii=False))
    print('Validated four pairs, derived materials, and rendered index.html')


if __name__=='__main__':main()
