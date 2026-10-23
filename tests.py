import unittest,tempfile,hashlib,base64,threading,io,json
from pathlib import Path
from PIL import Image
from engine import *
from media import recover_photos
from progress_view import STATE_COLORS,load_progress,matches_device,slider_byte_for_x

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.b=Path(self.tmp.name);self.src=self.b/'source.img';self.root=self.b/'job';self.root.mkdir()
        self.src.write_bytes(b'a'*BLOCK+b'b'*BLOCK);s=self.src.stat()
        save(self.root/'plan.json',dict(kind='file',source=str(self.src),size=s.st_size,mtime_ns=s.st_mtime_ns,sector=512,start=0,end=s.st_size,stage_bytes=s.st_size,guards=[]))
    def tearDown(self):self.tmp.cleanup()
    def reader(self,fail=None):
        src=self.src
        class Fake:
            def __init__(self,r):pass
            def read(self,a,n):
                if a==fail:raise TimeoutError('test timeout')
                with src.open('rb') as f:f.seek(a);b=f.read(n)
                return dict(data=base64.b64encode(b).decode(),seconds=.01)
            def close(self):pass
        return Fake
    def test_roundtrip(self):
        capture(self.root,threading.Event(),lambda x:None,self.reader());self.assertTrue(verify(self.root)['complete'])
        target=self.b/'restored.img';export_image(self.root,target);self.assertEqual(self.src.read_bytes(),target.read_bytes())
        before=records(self.root);capture(self.root,threading.Event(),lambda x:None,self.reader());self.assertEqual(before,records(self.root))
    def test_fault_no_retry(self):
        capture(self.root,threading.Event(),lambda x:None,self.reader(BLOCK));self.assertEqual(load(self.root/'status.json')['status'],'IO_TIMEOUT_UNCONFIRMED')
        self.assertFalse(verify(self.root)['complete']);before=records(self.root)
        capture(self.root,threading.Event(),lambda x:None,self.reader());self.assertEqual(before,records(self.root))
        with self.assertRaises(ValueError):export_image(self.root,self.b/'bad.img')

    def test_continuous_respects_stage_and_cumulative_limits(self):
        p=load(self.root/'plan.json');p['stage_bytes']=BLOCK;p['total_budget_bytes']=2*BLOCK;p['continuous']=True
        save(self.root/'plan.json',p)
        result=capture(self.root,threading.Event(),lambda x:None,self.reader())
        self.assertEqual(result['status'],'PLAN_BUDGET_COMPLETE')
        self.assertEqual(result['total_saved_bytes'],2*BLOCK)
        self.assertEqual(load(self.root/'status.json')['status'],'PLAN_BUDGET_COMPLETE')
        self.assertEqual(load(self.root/'continuous-status.json')['total_attempted_bytes'],2*BLOCK)

    def test_reconcile_received_bytes_without_source_access(self):
        payload=b'R'*BLOCK;name='chunk-000000000000.bin';(self.root/name).write_bytes(payload)
        digest=hashlib.sha256(payload).hexdigest();rid='already-read-request'
        append(self.root/'map.jsonl',dict(state='REQUESTED',request_id=rid,offset=0,length=BLOCK,file=name,file_offset=0))
        append(self.root/'map.jsonl',dict(state='RECEIVED',request_id=rid,offset=0,length=BLOCK,file=name,file_offset=0,sha256=digest))
        reconcile(self.root)
        self.assertTrue(any(r.get('request_id')==rid and r['state']=='GOOD' and r.get('reconciled') for r in records(self.root)))

    def test_reconcile_mismatch_remains_unconfirmed(self):
        payload=b'R'*BLOCK;name='chunk-000000000000.bin';(self.root/name).write_bytes(b'X'*BLOCK)
        rid='uncertain-request'
        append(self.root/'map.jsonl',dict(state='REQUESTED',request_id=rid,offset=0,length=BLOCK,file=name,file_offset=0))
        append(self.root/'map.jsonl',dict(state='RECEIVED',request_id=rid,offset=0,length=BLOCK,file=name,file_offset=0,sha256=hashlib.sha256(payload).hexdigest()))
        reconcile(self.root)
        rows=[r for r in records(self.root) if r.get('request_id')==rid]
        self.assertTrue(any(r['state']=='UNCONFIRMED' for r in rows))
        self.assertFalse(any(r['state']=='GOOD' for r in rows))

    def test_failure_classes_keep_startup_and_destination_distinct(self):
        self.assertEqual(classify_error(OSError(2,'missing reader'),'startup'),'ENGINE_START_FAILED')
        self.assertEqual(classify_error(OSError(55,'device unavailable'),'startup'),'SOURCE_DISCONNECTED')
        self.assertEqual(classify_error(OSError(23,'CRC'),'read'),'SOURCE_CRC_ERROR')
        self.assertEqual(classify_error(OSError(5,'denied'),'destination_write'),'DESTINATION_WRITE_FAILED')
        self.assertEqual(classify_error(OSError(5,'flush failed'),'destination_flush'),'DESTINATION_FLUSH_FAILED')
        self.assertEqual(classify_error(TimeoutError('slow'),'read'),'IO_TIMEOUT_UNCONFIRMED')

    def test_tamper(self):
        capture(self.root,threading.Event(),lambda x:None,self.reader());next(self.root.glob('chunk-*.bin')).write_bytes(b'bad')
        with self.assertRaises(ValueError):verify(self.root)
    def test_uncertain(self):
        append(self.root/'map.jsonl',dict(state='REQUESTED',offset=0,length=BLOCK))
        capture(self.root,threading.Event(),lambda x:None,self.reader());self.assertEqual(verify(self.root)['verified_bytes'],BLOCK)
    def test_recover_photo(self):
        im=Image.new('RGB',(160,120),'orange');buf=io.BytesIO();im.save(buf,format='JPEG');jpeg=buf.getvalue()
        self.src.write_bytes(jpeg+bytes(2*BLOCK-len(jpeg)));p=load(self.root/'plan.json');p['mtime_ns']=self.src.stat().st_mtime_ns;save(self.root/'plan.json',p)
        capture(self.root,threading.Event(),lambda x:None,self.reader());found=recover_photos(self.root);self.assertEqual(len(found),1);self.assertEqual(Path(found[0]['path']).read_bytes(),jpeg)
    def test_space_floor(self):
        from unittest.mock import patch
        from collections import namedtuple
        usage=namedtuple('usage','total used free')(FLOOR,FLOOR,0)
        with patch('engine.shutil.disk_usage',return_value=usage):capture(self.root,threading.Event(),lambda x:None,self.reader())
        self.assertEqual(records(self.root),[]);self.assertEqual(load(self.root/'status.json')['status'],'SPACE_LOW')
    def test_real_worker(self):
        capture(self.root,threading.Event(),lambda x:None)
        self.assertTrue(verify(self.root)['complete'])

    def test_physical_plan_approval_required_before_worker_start(self):
        from unittest.mock import patch
        plan=dict(version=2,plan_id='p1',kind='disk',number=3,serial='SERIAL',size=4096,sector=512,
            start=0,end=4096,stage_bytes=4096,guards=[],policy=dict(read_only=True,retries=0),
            destination_identity=dict(number=4,serial='DEST',size=8192))
        save(self.root/'plan.json',plan)
        called=[]
        def forbidden_reader(root):called.append(root);raise AssertionError('reader must not start')
        with patch('engine.validate'):
            with self.assertRaisesRegex(ValueError,'缺少審核紀錄'):
                capture(self.root,threading.Event(),lambda x:None,forbidden_reader)
        self.assertEqual(called,[])

    def test_approval_is_bound_to_exact_plan(self):
        from unittest.mock import patch
        plan=dict(version=2,plan_id='p2',kind='disk',number=3,serial='SERIAL',size=4096,sector=512,
            start=0,end=4096,stage_bytes=4096,guards=[],policy=dict(read_only=True,retries=0),
            destination_identity=dict(number=4,serial='DEST',size=8192))
        save(self.root/'plan.json',plan)
        with patch('engine.validate'):
            approve_physical_plan(self.root,'tester')
        require_physical_approval(self.root,plan)
        plan['end']=2048;save(self.root/'plan.json',plan)
        with self.assertRaisesRegex(ValueError,'計劃內容在審核後改變'):
            require_physical_approval(self.root,plan)

    def test_live_imported_exclusion_updates_invalidate_plan(self):
        import sys,types
        from engine import validate_live_exclusions
        source=self.b/'map-source';source.mkdir()
        plan=dict(kind='disk',serial='TESTDEVICE',imported_map_source=str(source),guards=[[100,200]],attempted=[[500,600]])
        fake=types.ModuleType('stream_scan');fake.exclusions=lambda: ([(100,200),(300,400)],[(500,600)])
        previous=sys.modules.get('stream_scan');sys.modules['stream_scan']=fake
        try:
            with self.assertRaises(ValueError):
                validate_live_exclusions(plan)
        finally:
            if previous is None:sys.modules.pop('stream_scan',None)
            else:sys.modules['stream_scan']=previous

    def test_physical_mutex_is_bound_to_serial(self):
        from engine import disk_mutex_name
        a=disk_mutex_name(dict(serial='same-physical-device',number=2))
        b=disk_mutex_name(dict(serial='same-physical-device',number=9))
        c=disk_mutex_name(dict(serial='other-device',number=2))
        self.assertEqual(a,b);self.assertNotEqual(a,c)

    def test_partition_preview_is_read_only_and_classified(self):
        from unittest.mock import patch
        from maintenance import preview
        plan=dict(version=2,plan_id='p3',kind='disk',number=3,serial='SERIAL',size=8*1024**2,sector=512,
            start=0,end=8*1024**2,stage_bytes=1024**2,guards=[],
            destination_identity=dict(number=4,serial='DEST',size=8192))
        save(self.root/'plan.json',plan)
        append(self.root/'map.jsonl',dict(state='GOOD',offset=1024**2,length=1024**2,file='chunk.bin',file_offset=0,sha256='x'))
        append(self.root/'map.jsonl',dict(state='FAILED',offset=3*1024**2,length=512,error='test'))
        append(self.root/'map.jsonl',dict(state='REQUESTED',offset=5*1024**2,length=512))
        append(self.root/'map.jsonl',dict(state='GUARD',start=3*1024**2,end=4*1024**2,reason='test guard'))
        fake_inventory=dict(disks=[],partitions=[dict(DiskNumber=3,PartitionNumber=1,DriveLetter='E',Offset=0,Size=8*1024**2)])
        with patch('platform_win.destination_identity',return_value=plan['destination_identity']), patch('maintenance.inventory',return_value=fake_inventory):
            path,report=preview(self.root)
        self.assertTrue(path.is_file())
        self.assertEqual(report['source_writes'],0)
        classes={x['classification'] for x in report['avoided_ranges']}
        self.assertIn('OBSERVED_READ_ERROR_NOT_PROVEN_PHYSICAL_BAD',classes);self.assertIn('UNCONFIRMED_REQUEST_DO_NOT_RETRY',classes);self.assertIn('POLICY_GUARD_NOT_PROVEN_BAD',classes)
        self.assertTrue(all(x['status']=='NOT_PROVEN_HEALTHY' for x in report['candidate_segments']))
        self.assertTrue(report['warnings'])

    def test_avoidance_export_preserves_attempted_classification(self):
        from media import avoidance
        p=load(self.root/'plan.json');p.update(kind='file',guards=[[512,1024]],attempted=[[2048,4096]])
        save(self.root/'plan.json',p)
        result=avoidance(self.root).read_text(encoding='utf-8-sig')
        self.assertIn('IMPORTED_POLICY_GUARD_NOT_PROVEN_BAD',result)
        self.assertIn('PREVIOUSLY_ATTEMPTED_NOT_PROVEN_BAD',result)

    def test_resume_with_json_guards(self):
        # JSON guards are lists; persisted requests become tuples in capture.
        p=load(self.root/'plan.json');p['guards']=[[0,512]];save(self.root/'plan.json',p)
        append(self.root/'map.jsonl',dict(state='REQUESTED',offset=512,length=512))
        capture(self.root,threading.Event(),lambda x:None,self.reader())
        self.assertEqual(verify(self.root)['verified_bytes'],p['size']-1024)
        self.assertEqual(verify(self.root)['missing_ranges'],[(0,1024)])

    def test_progress_band_loads_ranges_and_matches_exact_source(self):
        progress=self.b/'progress.json'
        progress.write_text(json.dumps(dict(schema='disk-rescue-progress/v1',source=dict(serial='SERIAL-1',size_bytes=4096),
            run=dict(status='RUNNING'),ranges=[dict(start=0,end=512,state='saved'),dict(start=512,end=2048,state='unknown')],overlays=[])),encoding='utf-8')
        data=load_progress(progress)
        self.assertEqual(STATE_COLORS['saved'],'#32965c')
        self.assertEqual(len(data['ranges']),2)
        self.assertTrue(matches_device(data,'serial-1',4096))
        self.assertFalse(matches_device(data,'OTHER',4096))
        self.assertFalse(matches_device(data,'SERIAL-1',8192))

    def test_progress_band_rejects_out_of_bounds_ranges_and_maps_slider(self):
        progress=self.b/'bad-progress.json'
        progress.write_text(json.dumps(dict(schema='disk-rescue-progress/v1',source=dict(serial='SERIAL-1',size_bytes=4096),
            ranges=[dict(start=0,end=8192,state='saved')])),encoding='utf-8')
        with self.assertRaises(ValueError):load_progress(progress)
        self.assertEqual(slider_byte_for_x(10,110,1024),0)
        self.assertEqual(slider_byte_for_x(110,110,1024),1024)
        self.assertEqual(slider_byte_for_x(60,110,1024,sector=512,end=600),0)

if __name__=='__main__':unittest.main()
