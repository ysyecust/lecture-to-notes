import hashlib
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from scripts.web_notes import ConversionError, build_web_notes, convert, digest, prepare_tex, safe_file

READY = all(shutil.which(x) for x in ('pandoc', 'identify'))

class WebNotesTests(unittest.TestCase):
    def test_blocks_source_file_access_and_unpaired_notes(self):
        for body in (r'\input{/etc/passwd}', r'\include{../secret}',r'\write18{touch file}',r'\srcnote{00:00:00--00:00:15}'):
            with self.assertRaises(ConversionError): prepare_tex(r'\begin{document}'+body+r'\end{document}')

    def test_blocks_path_escape_and_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'ok.tex').write_text('ok');(root/'link.tex').symlink_to(root/'ok.tex')
            for name in ('../ok.tex','/etc/passwd','link.tex'):
                with self.assertRaises(ConversionError):safe_file(root,name)

    @unittest.skipUnless(READY,'Pandoc and ImageMagick required')
    def test_preserves_source_notes_boxes_math_and_rejects_unknown_macros(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);Image.new('RGB',(10,10),'white').save(root/'figure.png')
            text=r'''\documentclass{article}
\begin{document}
\section{测试章节}
\begin{knowledgebox}{概念标题}正文含有 $x^2$。\end{knowledgebox}
\begin{figure}\includegraphics{figure.png}\caption{图注\protect\footnotemark}\end{figure}
\footnotetext{视频画面时间区间：00:00:00--00:00:15。}
\end{document}'''
            source=root/'notes.tex';source.write_text(text)
            spec={'expected':{'chapters':1,'figures':1,'images':1,'callouts':1,'tables':0,'math':1,'time_tokens':2},'resources':{'figure.png':digest(root/'figure.png')}}
            item={'id':'test','title':'测试','sha256':'pdf','source_url':'https://www.bilibili.com/video/BVtest/'}
            result=convert(source,root,root/'out',spec,item)
            html=(root/'out/article.html').read_text()
            self.assertEqual(result['status'],'passed');self.assertIn('00:00:15',html);self.assertIn('note-callout',html);self.assertIn('概念标题',html);self.assertIn('<math',html)
            self.assertEqual(result['counts']['figures'],1)
            source.write_text(text.replace('正文含有',r'\UnknownSemanticMacro{不应丢失}正文含有'))
            with self.assertRaises(ConversionError):convert(source,root,root/'bad',spec,item)
            source.write_text(text);Image.new('RGB',(10,10),'black').save(root/'figure.png')
            with self.assertRaisesRegex(ConversionError,'image hashes'):convert(source,root,root/'changed',spec,item)

    def test_failed_conversion_does_not_publish_html_or_reuse_old_output(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);course=root/'content/courses/a';course.mkdir(parents=True);(course/'notes.tex').write_text('changed')
            (course/'course.json').write_text(json.dumps({'items':[{'file':'a.pdf','web_source':{'tex':'notes.tex','sha256':'wrong','pdf_sha256':'pdf'}}]}))
            output=root/'out';(output/'notes/id').mkdir(parents=True);(output/'notes/id/article.html').write_text('old unchecked HTML')
            item={'id':'id','pdf':'pdfs/a.pdf','sha256':'pdf','web':{'article':'old'}}
            result=build_web_notes(root,output,{'items':[item]})
            self.assertEqual(result['id']['status'],'blocked');self.assertNotIn('web',item)
            self.assertFalse((output/'notes/id').exists());self.assertEqual(item['pdf'],'pdfs/a.pdf')

if __name__=='__main__':unittest.main()
