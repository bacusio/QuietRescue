import tempfile,unittest,json,hashlib,threading
from pathlib import Path
from photorec_session import normalize_session,resume_command,validate_checkpoint
class SessionTests(unittest.TestCase):
    def test_real_whole_image_order_255(self):
        data,info=self.case(command='partition_none,255,blocksize,65536,fileopt,everything,disable,jpg,enable,options,paranoid,keep_corrupted_file_no,wholespace,search,status=find_offset,inter')
        self.assertIn(b'partition_none,255,',data)
        self.assertEqual(info['remaining_sectors'],8)
    def test_arbitrary_partition_order_rejected(self):
        with self.assertRaises(ValueError):
            self.case(command='partition_none,1,fileopt,everything,disable,jpg,enable,search,inter')
    def attempt(self,job,*,confirmed=True,missing=False):
        state=json.loads((job/'recovery.json').read_text())
        attempt=job/('resume-'+'a'*32);attempt.mkdir()
        state['resume_attempt']=str(attempt)
        (job/'recovery.json').write_text(json.dumps(state))
        (attempt/'resume.json').write_text(json.dumps(dict(status='STOPPED_ERROR',worker_exit_confirmed=confirmed,input_sha256=state['input_sha256'])))
        if not missing:
            data=(job/'photorec.ses').read_text().replace('0-7','4-7')
            (attempt/'photorec.ses').write_text(data)
    def test_latest_attempt_selected_not_original(self):
        result=self.checkpoint(self.attempt)
        self.assertEqual(result[3]['ranges'],[(4,7)])
    def test_missing_latest_does_not_fall_back(self):
        with self.assertRaisesRegex(ValueError,'no fallback'):
            self.checkpoint(lambda j:self.attempt(j,missing=True))
    def test_unconfirmed_worker_blocks_resume(self):
        with self.assertRaisesRegex(ValueError,'unconfirmed'):
            self.checkpoint(lambda j:self.attempt(j,confirmed=False))
    def checkpoint(self,mutation=None):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            job=Path(t);p=job/'input.img';p.write_bytes(bytes(4096))
            from image_recovery import ascii_path
            state=dict(status='STOPPED_ERROR',source_bytes=4096,input_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
            (job/'recovery.json').write_text(json.dumps(state))
            (job/'photorec.ses').write_text('#123\n'+ascii_path(p).replace('\\','/')+' partition_none,0,fileopt,everything,disable,jpg,enable,wholespace,search,status=ext2_off,0,inter\n0-7\n')
            if mutation:mutation(job)
            originals={str(x.relative_to(job)):x.read_bytes() for x in job.rglob('*') if x.is_file()}
            result=validate_checkpoint(job,threading.Event())
            self.assertEqual(originals,{str(x.relative_to(job)):x.read_bytes() for x in job.rglob('*') if x.is_file()})
            return result
    def test_checkpoint_verified_without_mutation(self):
        self.assertEqual(self.checkpoint()[3]['remaining_sectors'],8)
    def test_checkpoint_corruption_rejected(self):
        with self.assertRaisesRegex(ValueError,'hash changed'):
            self.checkpoint(lambda j:(j/'input.img').write_bytes(b'X'+bytes(4095)))
    def test_checkpoint_missing_session_not_restart(self):
        with self.assertRaisesRegex(ValueError,'incomplete'):
            self.checkpoint(lambda j:(j/'photorec.ses').unlink())
    def test_checkpoint_unverified_copy_rejected(self):
        with self.assertRaisesRegex(ValueError,'not verified'):
            self.checkpoint(lambda j:(j/'recovery.json').write_text(json.dumps(dict(status='STOPPED_ERROR',source_bytes=4096))))
    def test_resume_explicit_image_precedes_command(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            p=Path(t)/'input.img';p.write_bytes(bytes(4096))
            args=resume_command('photorec_win.exe',p,Path(t)/'recovered')
            self.assertEqual(args[1],str(p.resolve()).replace('\\','/'))
            self.assertEqual(args[4:],['/cmd','resume','/log'])
    def test_resume_missing_image_rejected(self):
        with self.assertRaises(ValueError):
            resume_command('photorec_win.exe',Path(__file__).parent/'absent.img','out')
    def case(self,command=None,device=None,ranges='0-7',suffix=b''):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as t:
            p=Path(t)/'input.img';p.write_bytes(bytes(4096))
            from image_recovery import ascii_path
            raw=('#123\n'+(device or ascii_path(p).replace('\\','/'))+' '+(command or 'partition_none,0,fileopt,everything,disable,jpg,enable,wholespace,search,status=ext2_off,0,inter')+'\n'+ranges+'\n').encode()+suffix
            return normalize_session(raw,p)
    def test_normalized_private_copy(self):
        data,info=self.case(suffix=bytes(40960));self.assertNotIn(b',inter',data);self.assertEqual(info['remaining_sectors'],8)
    def test_physical_device_rejected(self):
        with self.assertRaises(ValueError):self.case(device='\\\\.\\PhysicalDrive4')
    def test_unknown_command_rejected(self):
        with self.assertRaises(ValueError):self.case(command='partition_none,0,fileopt,write,search,inter')
    def test_out_of_bounds(self):
        with self.assertRaises(ValueError):self.case(ranges='0-8')
    def test_overlap(self):
        with self.assertRaises(ValueError):self.case(ranges='0-4\n4-7')
    def test_hidden_payload_rejected(self):
        with self.assertRaises(ValueError):self.case(suffix=b'\x00evil')
if __name__=='__main__':unittest.main()
