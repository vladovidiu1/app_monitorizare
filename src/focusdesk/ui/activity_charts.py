"""Small native, keyboard-operable Canvas charts using FocusDesk design tokens."""
import tkinter as tk
from tkinter import ttk
from .design import C, px
from ..domain.labels import format_seconds


class BarChart(ttk.Frame):
    def __init__(self,parent,title,*,horizontal=False,on_select=lambda token:None):
        super().__init__(parent,style='Card.TFrame',padding=12)
        self.horizontal=horizontal;self.on_select=on_select;self.rows=[];self.selected=0
        self.title=ttk.Label(self,text=title,style='Section.TLabel');self.title.pack(anchor='w')
        self.caption=ttk.Label(self,style='Muted.TLabel');self.caption.pack(anchor='w',pady=(2,4))
        self.canvas=tk.Canvas(self,height=px(self,190),background=C.surface,highlightthickness=1,
                              highlightbackground=C.border,highlightcolor=C.accent,takefocus=True)
        self.canvas.pack(fill='both',expand=True)
        self.hbar=ttk.Scrollbar(self,orient='horizontal',command=self.canvas.xview)
        self.hbar.pack(fill='x');self.canvas.configure(xscrollcommand=self.hbar.set)
        self.hint=ttk.Label(self,text='Săgeți: selectare · Enter: filtrează · detalii exacte în tabele',style='Muted.TLabel',wraplength=520)
        self.hint.pack(anchor='w',pady=(4,0))
        self.canvas.bind('<Configure>',lambda event:self.draw())
        for key,delta in (('<Left>',-1),('<Up>',-1),('<Right>',1),('<Down>',1)):
            self.canvas.bind(key,lambda event,d=delta:self.move(d))
        self.canvas.bind('<Return>',lambda event:self.activate())
        self.canvas.bind('<space>',lambda event:self.activate())
        self.canvas.bind('<FocusIn>',lambda event:self.draw())
        self.canvas.bind('<FocusOut>',lambda event:self.draw())

    def set_rows(self,rows,caption=''):
        self.rows=rows;self.selected=min(self.selected,max(0,len(rows)-1))
        self.caption.configure(text=caption);self.draw()

    def move(self,delta):
        self.selected=max(0,min(len(self.rows)-1,self.selected+delta));self.draw()
        if self.rows:
            row=self.rows[self.selected]
            self.hint.configure(text=f"{row['label']}: {format_seconds(row['value'])}"+(f" lucrat / {format_seconds(row['secondary'])} programat" if 'secondary' in row else '')+' · Enter: filtrează')
            if not self.horizontal:self.canvas.xview_moveto(max(0,(self.selected-2)/len(self.rows)))
        return 'break'

    def activate(self):
        if self.rows:self.on_select(self.rows[self.selected]['token'])
        return 'break'

    def click(self,index):
        self.selected=index;self.canvas.focus_set();self.activate()

    def draw(self):
        c=self.canvas;c.delete('all');width=max(px(self,280),c.winfo_width());height=px(self,190)
        family=self._root()._focusdesk_family
        font=(family,9)
        if not self.rows:
            c.create_text(width/2,height/2,text='Nicio durată în intervalul ales',fill=C.muted,font=font)
            c.configure(scrollregion=(0,0,width,height));return
        maximum=max(max(row['value'],row.get('secondary',0)) for row in self.rows) or 1
        if self.horizontal:
            for i,row in enumerate(self.rows):
                y=px(self,12)+i*px(self,29)
                name=row['label'] if len(row['label'])<28 else row['label'][:25]+'…'
                c.create_text(px(self,8),y+px(self,9),text=name,anchor='w',fill=C.text,font=font,tags=(f'bar{i}',))
                left=width*.43;right=width-px(self,74)
                c.create_rectangle(left,y,left+max(2,(right-left)*row['value']/maximum),y+px(self,17),fill=C.accent,outline='',tags=(f'bar{i}',))
                c.create_text(width-px(self,5),y+px(self,9),text=f"{row['value']/3600:.1f} h",anchor='e',fill=C.text,font=font,tags=(f'bar{i}',))
                c.tag_bind(f'bar{i}','<Button-1>',lambda event,n=i:self.click(n))
                if i==self.selected and c.focus_get() is c:c.create_rectangle(1,y-2,width-2,y+px(self,22),outline=C.accent,dash=(3,2))
            c.configure(scrollregion=(0,0,width,height))
        else:
            step=max(px(self,18),(width-px(self,50))/len(self.rows));virtual=max(width,step*len(self.rows)+px(self,50))
            base=height-px(self,27);plot=height-px(self,54)
            c.create_line(px(self,32),base,virtual,base,fill=C.border)
            c.create_text(px(self,4),px(self,9),text=f'{maximum/3600:.1f} h',anchor='nw',fill=C.muted,font=font)
            for i,row in enumerate(self.rows):
                x=px(self,38)+i*step;bw=max(2,step*.34)
                c.create_rectangle(x,base-plot*row['value']/maximum,x+bw,base,fill=C.accent,outline='',tags=(f'bar{i}',))
                c.create_rectangle(x+bw+1,base-plot*row.get('secondary',0)/maximum,x+2*bw+1,base,fill=C.border,outline=C.muted,tags=(f'bar{i}',))
                if i%max(1,len(self.rows)//8)==0:
                    c.create_text(x,base+px(self,12),text=row['label'],anchor='n',fill=C.muted,font=(family,8))
                c.create_rectangle(x,px(self,25),x+step-2,base,fill='',outline=C.accent if i==self.selected and c.focus_get() is c else '',tags=(f'bar{i}',))
                c.tag_bind(f'bar{i}','<Button-1>',lambda event,n=i:self.click(n))
            c.configure(scrollregion=(0,0,virtual,height))
