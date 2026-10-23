"""Read-only partition-layout preview. This module contains no disk-write API."""
import csv
from pathlib import Path

from engine import load, records, merge, remaining, save, validate_saved_output
from platform_win import inventory

ALIGNMENT=1024*1024

def preview(root):
    root=Path(root).resolve();plan=load(root/'plan.json');validate_saved_output(plan,root)
    if plan.get('kind')!='disk':raise ValueError('避讓預覽只支援實體磁碟任務')
    size=int(plan['size']);sector=int(plan['sector'])
    rows=records(root);avoid=[];good=[]
    for row in rows:
        if row['state']=='GOOD':good.append((int(row['offset']),int(row['offset'])+int(row['length'])))
        elif row['state'] in ('FAILED','REQUESTED','UNCONFIRMED'):
            a=int(row['offset'])
            label={'FAILED':'OBSERVED_READ_ERROR_NOT_PROVEN_PHYSICAL_BAD',
                'REQUESTED':'UNCONFIRMED_REQUEST_DO_NOT_RETRY',
                'UNCONFIRMED':'UNCONFIRMED_REQUEST_DO_NOT_RETRY'}[row['state']]
            avoid.append(dict(start=a,end=a+int(row['length']),classification=label,evidence=row.get('failure_class',row['state'])))
        elif row['state']=='GUARD':
            avoid.append(dict(start=int(row['start']),end=int(row['end']),classification='POLICY_GUARD_NOT_PROVEN_BAD',evidence=row.get('reason','GUARD')))
    for a,z in plan.get('guards',[]):avoid.append(dict(start=int(a),end=int(z),classification='IMPORTED_POLICY_GUARD_NOT_PROVEN_BAD',evidence='APPROVED_PLAN_BASELINE'))
    for a,z in plan.get('attempted',[]):avoid.append(dict(start=int(a),end=int(z),classification='PREVIOUSLY_ATTEMPTED_NOT_PROVEN_BAD',evidence='APPROVED_PLAN_BASELINE'))
    avoid.extend([
        dict(start=0,end=min(size,ALIGNMENT),classification='GPT_METADATA_RESERVE_ESTIMATE',evidence='PREVIEW_ONLY'),
        dict(start=max(0,size-ALIGNMENT),end=size,classification='GPT_METADATA_RESERVE_ESTIMATE',evidence='PREVIEW_ONLY')])
    clipped=[]
    for row in avoid:
        a=max(0,min(size,row['start']));z=max(0,min(size,row['end']))
        if a<z:clipped.append({**row,'start':a,'end':z})
    blocked=merge([(x['start'],x['end']) for x in clipped])
    alignment=max(ALIGNMENT,sector)
    candidate=[]
    for a,z in remaining(0,size,blocked):
        left=((a+alignment-1)//alignment)*alignment
        right=(z//alignment)*alignment
        if left<right:candidate.append(dict(start=left,end=right,bytes=right-left,status='NOT_PROVEN_HEALTHY'))
    known=merge([(max(0,a),min(size,z)) for a,z in good if max(0,a)<min(size,z)])
    known_bytes=sum(z-a for a,z in known)
    try:
        devices=inventory();matches=[d for d in devices['disks'] if str(d.get('SerialNumber') or '').strip()==plan['serial'] and int(d['Size'])==size]
        if len(matches)!=1:
            current=[];inventory_note='來源實體磁碟目前缺席或身份不唯一；不顯示目前分區資料。'
        else:
            current=[dict(partition_number=int(p['PartitionNumber']),drive_letter=p.get('DriveLetter'),offset=int(p['Offset']),size=int(p['Size']))
                     for p in devices['partitions'] if int(p['DiskNumber'])==int(matches[0]['Number'])]
            inventory_note=''
    except Exception as e:
        current=[];inventory_note='無法讀取目前分區清單：'+str(e)
    report=dict(schema_version=1,mode='READ_ONLY_PARTITION_PREVIEW',source=dict(number=plan['number'],serial=plan['serial'],size=size,logical_sector_bytes=sector),
        scope=dict(start=plan['start'],end=plan['end']),current_partitions=current,avoided_ranges=clipped,candidate_segments=candidate,
        recorded_good_bytes=known_bytes,scope_bytes=int(plan['end'])-int(plan['start']),
        unverified_bytes=max(0,size-known_bytes),alignment_bytes=alignment,source_writes=0,
        warnings=['候選段只表示未被目前地圖標為故障或策略保護；未讀區仍未證實健康。',
                  '候選段預覽不能阻止原始磁碟寫入，不能修復物理故障，也不會修改現有分區。',
                  '執行新分區會改寫分區表並可能失去現有資料；本版本不提供執行入口。'])
    if inventory_note:report['warnings'].append(inventory_note)
    save(root/'partition-preview.json',report)
    with (root/'partition-preview.csv').open('w',newline='',encoding='utf-8-sig') as f:
        w=csv.writer(f);w.writerow(['start_byte','end_exclusive_byte','classification','status','evidence'])
        for x in clipped:w.writerow([x['start'],x['end'],x['classification'],'BLOCKED',x['evidence']])
        for x in candidate:w.writerow([x['start'],x['end'],'CANDIDATE_SEGMENT',x['status'],'NOT_PROVEN_HEALTHY'])
        for x in current:w.writerow([x['offset'],x['offset']+x['size'],'CURRENT_PARTITION','EXISTING',x['drive_letter'] or ''])
    return root/'partition-preview.json',report
