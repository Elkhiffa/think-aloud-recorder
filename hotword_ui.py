"""Manual terminology editor with local SCEL/TXT import and dictionary links."""
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

from hotword_files import (MAX_WORDS, SOGOU_DICTIONARIES, dictionary_search_url,
                          merge_files, split_words)


class HotwordEditor(ttk.Frame):
    def __init__(self, parent, value='', *, game_name=lambda: '', directory=None, qwen=True):
        super().__init__(parent)
        self.game_name = game_name
        self.directory = Path(directory) if directory else Path.home() / 'Downloads'
        if not self.directory.is_dir():
            self.directory = Path.home()
        self.qwen = qwen
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.editor = tk.Text(self, height=4, wrap='word', undo=True, font=('Microsoft YaHei UI', 10))
        self.editor.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(self, orient='vertical', command=self.editor.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.editor.configure(yscrollcommand=scroll.set)
        self.editor.insert('1.0', value)
        bar = ttk.Frame(self)
        bar.grid(row=1, column=0, columnspan=2, sticky='ew', pady=(6, 0))
        self.import_button = ttk.Button(bar, text='选择词库文件…', command=self.import_files)
        self.import_button.pack(side='left')
        self.search_button = ttk.Button(bar, text='搜狗搜索词库', command=lambda: self.open_url(dictionary_search_url(self.game_name())))
        self.search_button.pack(side='left', padx=5)
        self.website_button = ttk.Button(bar, text='词库下载网站', command=lambda: self.open_url(SOGOU_DICTIONARIES))
        self.website_button.pack(side='left')
        self.count = tk.StringVar()
        ttk.Label(bar, textvariable=self.count).pack(side='right', padx=(5, 0))
        self.status = tk.StringVar(value='可手动输入，逗号或换行分隔。支持 .scel / .txt，导入会合并去重。')
        ttk.Label(self, textvariable=self.status, wraplength=620).grid(row=2, column=0, columnspan=2, sticky='w', pady=(5, 0))
        self.editor.bind('<<Modified>>', self.changed)
        self.changed()

    def get(self):
        return self.editor.get('1.0', 'end-1c')

    def changed(self, event=None):
        self.count.set(f'{len(split_words(self.get()))} / {MAX_WORDS} 词')
        if self.editor.edit_modified():
            self.editor.edit_modified(False)

    def import_files(self):
        paths = filedialog.askopenfilenames(parent=self.winfo_toplevel(), title='选择词库文件（可多选）',
            initialdir=str(self.directory), filetypes=(('支持的词库', '*.scel *.txt'), ('搜狗细胞词库', '*.scel'), ('纯文本词库', '*.txt')))
        if not paths:
            return
        try:
            words, added = merge_files(self.get(), paths, qwen=self.qwen)
        except (OSError, ValueError) as error:
            messagebox.showerror('词库未导入', str(error), parent=self.winfo_toplevel())
            return
        self.editor.edit_separator()
        self.editor.delete('1.0', 'end')
        self.editor.insert('1.0', '\n'.join(words))
        self.editor.edit_separator()
        self.changed()
        self.directory = Path(paths[0]).parent
        self.status.set(f'已合并 {len(paths)} 个文件，新增 {added} 个词。可继续编辑；保存预设后无需保留原文件。')

    def open_url(self, url):
        try:
            if not webbrowser.open(url):
                raise OSError('未能打开默认浏览器，请手动访问搜狗词库网站。')
        except OSError as error:
            messagebox.showerror('打开词库网站', str(error), parent=self.winfo_toplevel())
