import unittest,threading,queue
from unittest.mock import patch
from partition_scan import analyze
from app import App
class ModeTests(unittest.TestCase):
    def test_arbitrary_commands_rejected_before_file_access(self):
        with patch('partition_scan.Path',side_effect=AssertionError('Input must not be accessed')):
            with self.assertRaises(ValueError):analyze('unused','unused',threading.Event(),table='gpt,write')
    def test_ui_gpt_dispatch(self):
        a=App.__new__(App);a.busy=False;a.root=None;a.stop=threading.Event();a.events=queue.Queue();messages=[]
        a.job=lambda f,operation:messages.append(f())
        with patch('app.filedialog.askopenfilename',return_value='synthetic.img'),patch('app.filedialog.askdirectory',return_value='output'),patch('app.simpledialog.askstring',return_value=' GPT '),patch('app.destination_identity',return_value={'serial':'DESTINATION'}),patch('partition_scan.analyze',return_value={'output':'output'}) as call:
            a.scan_partitions();self.assertEqual(call.call_args.kwargs['table'],'gpt');self.assertTrue(messages)
    def test_ui_cancel_does_not_launch(self):
        a=App.__new__(App);a.busy=False;a.job=lambda *a,**k:self.fail('unexpected launch')
        with patch('app.filedialog.askopenfilename',return_value='synthetic.img'),patch('app.filedialog.askdirectory',return_value='output'),patch('app.simpledialog.askstring',return_value=None):a.scan_partitions()
if __name__=='__main__':unittest.main()
