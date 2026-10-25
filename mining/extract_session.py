"""Condense one Claude Code session transcript into a chronological, scrubbed conversation for lesson mining.

Keeps only what people said: user prompts (including messages sent mid-turn) and the assistant's prose replies.
Drops tool calls, tool output, thinking, attachments and request metadata. Personal data is scrubbed before writing.

    python mining/extract_session.py <session.jsonl> <out.md>
"""
import json,re,sys
from pathlib import Path

SCRUB=[(re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'),'<email>'),
       (re.compile(r'/home/[^/\s]+'),'~'),
       (re.compile(r'\b(gh[opsu]_[A-Za-z0-9]{8,}|sk-[A-Za-z0-9-]{12,})\b'),'<token>'),
       (re.compile(r'\b\d{1,3}(\.\d{1,3}){3}\b'),'<ip>'),
       (re.compile(r'/tmp/claude-\d+/[^\s)]+'),'<scratch>')]

def scrub(s):
    for rx,rep in SCRUB:s=rx.sub(rep,s)
    return s

def texts(content):
    if isinstance(content,str):return [content]
    out=[]
    for b in content or []:
        if isinstance(b,dict) and b.get('type')=='text':out.append(b.get('text',''))
    return out

def main(src,dst):
    rows=[]
    for line in open(src,encoding='utf-8'):
        try:d=json.loads(line)
        except ValueError:continue
        t=d.get('type');ts=d.get('timestamp','')
        if d.get('isSidechain'):continue
        if t=='user':
            for s in texts(d.get('message',{}).get('content')):
                s=s.strip()
                # Harness wrappers (reminders, notifications, command echoes) are not the user's words.
                if not s or s.startswith(('<system-reminder','<task-notification','<command-','Caveat:','[Request interrupted')):continue
                rows.append((ts,'USER',s))
        elif t=='queue-operation' and d.get('operation')=='enqueue' and isinstance(d.get('content'),str):
            rows.append((ts,'USER (mid-turn)',d['content'].strip()))
        elif t=='assistant':
            for s in texts(d.get('message',{}).get('content')):
                s=s.strip()
                if s:rows.append((ts,'ASSISTANT',s))
    out=[f'# Condensed session transcript\n\nSource: {Path(src).name} (scrubbed; prose only)\n']
    prev=None
    for ts,who,s in rows:
        if (who,s)==prev:continue
        prev=(who,s);out.append(f'\n## {ts[:19]} {who}\n\n{scrub(s)}\n')
    Path(dst).parent.mkdir(parents=True,exist_ok=True);Path(dst).write_text(''.join(out),encoding='utf-8')
    users=sum(1 for _,w,_ in rows if w.startswith('USER'));print(f'{len(rows)} entries ({users} from the user) -> {dst} ({Path(dst).stat().st_size//1024} KB)')

if __name__=='__main__':main(*sys.argv[1:3])
