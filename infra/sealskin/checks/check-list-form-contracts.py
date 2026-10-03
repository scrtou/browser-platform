#!/usr/bin/env python3
"""Compare rendered form contracts before/after presentation-only changes."""
import argparse
from collections import Counter
from html.parser import HTMLParser
import json
from pathlib import Path

class Forms(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.forms=[];self.current=None;self.control=None
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='form':
            assert self.current is None,'nested form'
            self.current={'method':a.get('method','get'),'action':a.get('action',''),'controls':[]}
        if self.current is not None and tag in ('input','select','textarea','button','option'):
            if tag=='button' and not a.get('name'):return
            keep=('name','type','value','required','disabled','checked','selected','multiple','min','max','minlength','maxlength','pattern','form','formaction','formmethod')
            value={'tag':tag,**{k:v for k,v in a.items() if k in keep}}
            if a.get('name')=='csrf' and a.get('value'):
                value['value']='<per-request-csrf>'
            self.current['controls'].append(value)
            if tag=='textarea':self.control=value;value['text']=''
    def handle_data(self,data):
        if self.control is not None:self.control['text']+=data
    def handle_endtag(self,tag):
        if tag=='textarea':self.control=None
        if tag=='form':
            assert self.current is not None,'orphan form close'
            self.forms.append(self.current);self.current=None
    def contracts(self):
        assert self.current is None,'unclosed form'
        return Counter(json.dumps(f,sort_keys=True,ensure_ascii=False) for f in self.forms)

def main():
    p=argparse.ArgumentParser();p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    results=[]
    for path in sorted(a.before.rglob('*.json')):
        new=a.after/path.relative_to(a.before)
        if not new.exists():continue
        old=json.loads(path.read_text());updated=json.loads(new.read_text())
        if not isinstance(old,dict) or 'body' not in old:continue
        x=Forms();x.feed(old['body']);y=Forms();y.feed(updated['body'])
        assert x.contracts()==y.contracts(),str(path.relative_to(a.before))
        results.append({'fixture':str(path.relative_to(a.before)),'forms':len(x.forms)})
    assert len(results)>=20,'missing fixtures'
    a.output.write_text(json.dumps({'result':'PASS','fixtures':results,'forms':sum(v['forms'] for v in results)},indent=2)+'\n')
    print('PASS',len(results),'fixtures;',sum(v['forms'] for v in results),'unchanged form contracts')
if __name__=='__main__':main()
