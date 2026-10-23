import unittest,threading,queue
from unittest.mock import patch
from app import App

class ResumeUI(unittest.TestCase):
    def app(self):
        a=App.__new__(App);a.busy=False;a.root=None
        a.stop=threading.Event();a.events=queue.Queue()
        a.job=lambda fn,operation:fn()
        return a
    def test_dispatches_saved_job(self):
        a=self.app()
        with patch('app.filedialog.askdirectory',return_value='saved-job'),patch('app.destination_identity',return_value={'serial':'HEALTHY'}),patch('photorec_resume.resume',return_value={'recovered_files':1,'output':'saved-job/resume'}) as call:
            a.resume_photorec();self.assertEqual(call.call_args.args[0],'saved-job')
            self.assertIs(call.call_args.args[1],a.stop)
    def test_cancel_no_launch(self):
        a=self.app();a.job=lambda *args,**kwargs:self.fail('Unexpected launch')
        with patch('app.filedialog.askdirectory',return_value=''):a.resume_photorec()
    def test_unknown_destination_no_launch(self):
        a=self.app();a.job=lambda *args,**kwargs:self.fail('Unexpected launch')
        with patch('app.filedialog.askdirectory',return_value='saved-job'),patch('app.destination_identity',return_value={}),patch('app.messagebox.showerror') as error:
            a.resume_photorec();error.assert_called_once()
    def test_source_destination_no_launch(self):
        from pathlib import Path
        a=self.app();a.root=Path('task');a.job=lambda *args,**kwargs:self.fail('Unexpected launch')
        with patch('app.filedialog.askdirectory',return_value='saved-job'),patch('app.destination_identity',return_value={'serial':'SOURCE'}),patch('app.load',return_value={'kind':'disk','serial':'SOURCE'}),patch('app.messagebox.showerror') as error:
            a.resume_photorec();error.assert_called_once()

if __name__=='__main__':unittest.main()
