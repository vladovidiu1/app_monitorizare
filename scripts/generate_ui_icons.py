"""Generate the original FocusDesk outline icons (MIT). Development only, not runtime."""
from pathlib import Path
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]/'src/focusdesk/resources/icons'
ROOT.mkdir(parents=True,exist_ok=True)
SHAPES={
 'stop':[('rect',(6,6,18,18))],
 'clear':[('line',(6,6,18,18)),('line',(6,18,18,6))],
 'up':[('line',(5,15,12,8,19,15))],
 'down':[('line',(5,9,12,16,19,9))],
 'left':[('line',(15,5,8,12,15,19))],
 'right':[('line',(9,5,16,12,9,19))],
 'today': [('rect',(4,5,20,21)),('line',(4,10,20,10)),('line',(8,3,8,7)),('line',(16,3,16,7)),('line',(8,14,11,14))],
 'calendar':[('rect',(4,5,20,21)),('line',(4,10,20,10)),('line',(8,3,8,7)),('line',(16,3,16,7)),('line',(8,14,16,14)),('line',(8,17,16,17))],
 'inbox':[('rect',(3,5,21,20)),('line',(3,14,8,14,10,17,14,17,16,14,21,14))],
 'mail':[('rect',(3,5,21,19)),('line',(3,6,12,13,21,6))],
 'waiting':[('ellipse',(3,3,21,21)),('line',(12,7,12,12,16,14))],
 'overdue':[('line',(6,22,6,3,19,3,16,8,19,13,6,13))],
 'archive':[('rect',(4,8,20,21)),('rect',(3,3,21,8)),('line',(9,12,15,12))],
 'folder':[('line',(3,20,3,5,10,5,12,8,21,8,21,20,3,20))],
 'project':[('rect',(4,5,20,21)),('line',(9,5,9,3,15,3,15,5)),('line',(8,11,16,11)),('line',(8,16,13,16))],
 'task':[('rect',(4,3,20,21)),('line',(8,12,11,15,17,8))],
 'assistant':[('rect',(3,4,21,18)),('line',(6,18,6,22,11,18)),('line',(8,10,16,10)),('line',(8,14,13,14))],
 'search':[('ellipse',(3,3,16,16)),('line',(15,15,22,22))],
 'chart':[('line',(3,3,3,21,22,21)),('line',(7,17,7,12)),('line',(12,17,12,7)),('line',(17,17,17,4))],
 'play':[('line',(7,4,20,12,7,20,7,4))],
 'add':[('line',(12,4,12,20)),('line',(4,12,20,12))],
 'settings':[('line',(3,6,21,6)),('line',(3,12,21,12)),('line',(3,18,21,18)),('ellipse',(6,3,12,9)),('ellipse',(13,9,19,15)),('ellipse',(5,15,11,21))],
 'brand':[('rect',(3,3,21,21)),('line',(8,17,8,7,17,7)),('line',(8,12,15,12))],
}
for name,shapes in SHAPES.items():
 im=Image.new('RGBA',(96,96));d=ImageDraw.Draw(im)
 for shape,points in shapes:
  coords=tuple(p*4 for p in points)
  if shape=='line':d.line(coords,fill='#596579',width=7,joint='curve')
  else:getattr(d,'rectangle' if shape=='rect' else shape)(coords,outline='#596579',width=7)
 for size in (16,20,24,32,40,48):
  im.resize((size,size),Image.Resampling.LANCZOS).save(ROOT/f'{name}-{size}.png')
  if name in ('play','assistant','add'):
   white=Image.new('RGBA',im.size,'white');white.putalpha(im.getchannel('A'))
   white.resize((size,size),Image.Resampling.LANCZOS).save(ROOT/f'{name}-on-accent-{size}.png')
