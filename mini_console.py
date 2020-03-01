from __future__ import annotations
from typing import *
import os, threading, functools, re
import data, functions, weakref, components, platform
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import urllib.request
import urllib.error
import socket
import components.thread_switcher  as _sw_
import gui.stylesheets.scrollbar   as _sb_
import bpathlib.file_power         as _fp_
import bpathlib.path_power         as _pp_
import mini_console.process        as _pr_
import gui.stylesheets.progressbar as _progbar_style_
nop = lambda *a, **k: None


class MiniConsole(QWidget):
    startSignal = pyqtSignal()
    closeSignal = pyqtSignal(bool)

    set_extprogbar_val_sig = pyqtSignal(int)
    set_extprogbar_max_sig = pyqtSignal(int)
    set_extprogbar_inf_sig = pyqtSignal(bool)

    def __init__(self, title:str) -> None:
        super().__init__()
        assert threading.current_thread() is threading.main_thread()
        self.setGeometry(100, 100, 1500, 600)
        self.setWindowTitle(title)
        self.setStyleSheet("QWidget { background-color: #ffffffff }")
        self.__lyt = QVBoxLayout()
        self.__lyt.setAlignment(Qt.AlignTop)
        self.setLayout(self.__lyt)
        # Mini console
        self.__miniEditor = MiniEditor()
        self.__process = _pr_.Process()
        self.__process.output_sig.connect(self.__miniEditor._printout_)
        self.__process.output_sig.connect(self.log_output)
        self.__process.output_html_sig.connect(self.__miniEditor._printout_html_)
        # Layouts
        self.__lyt.addWidget(self.__miniEditor)
        self.show()
        self.__isclosed = False
        # External progbar
        self.__extprogbar:QProgressBar = None
        self.__extprogbar_active:bool  = False
        self.__progbar_incr_chars:str  = '\n'
        self.__extprogbar_val:int      = 0
        self.set_extprogbar_val_sig.connect(self.set_extprogbar_val)
        self.set_extprogbar_max_sig.connect(self.set_extprogbar_max)
        self.set_extprogbar_inf_sig.connect(self.set_extprogbar_fad)
        return

    """
    1. BASIC FUNCTIONS
    """
    def connect_signals(self, startfunc:Callable=None, closefunc:Callable=None) -> None:
        if startfunc is not None:
            self.startSignal.connect(startfunc)
        if closefunc is not None:
            self.closeSignal.connect(closefunc)
        return

    def detach_signals(self) -> None:
        def discon_sig(signal):
            while True:  # Disconnect only breaks one connection at a time,
                try:     # so loop to be safe.
                    signal.disconnect()
                except TypeError:
                    break
            return
        discon_sig(self.startSignal)
        discon_sig(self.closeSignal)
        return

    def start(self) -> None:
        self.startSignal.emit()
        return

    def close(self) -> None:
        QWidget.close(self)
        return

    def closeEvent(self, event:QCloseEvent) -> None:
        self.__isclosed = True
        self.closeSignal.emit(False)
        super().closeEvent(event)
        return

    def is_closed(self) -> bool:
        return self.__isclosed

    def assign_external_progbar(self, progbar:QProgressBar) -> None:
        assert threading.current_thread() is threading.main_thread()
        self.__extprogbar = progbar
        return

    @pyqtSlot(int)
    def set_extprogbar_val(self, val:int) -> None:
        if self.__extprogbar is None:
            return
        if threading.current_thread() is not threading.main_thread():
            self.set_extprogbar_val_sig.emit(val)
            return
        assert threading.current_thread() is threading.main_thread()
        self.__extprogbar.setValue(val)
        return

    @pyqtSlot(int)
    def set_extprogbar_max(self, val:int) -> None:
        if self.__extprogbar is None:
            return
        if threading.current_thread() is not threading.main_thread():
            self.set_extprogbar_max_sig.emit(val)
            return
        assert threading.current_thread() is threading.main_thread()
        self.__extprogbar.setMaximum(val)
        return

    @pyqtSlot(bool)
    def set_extprogbar_fad(self, fad:bool) -> None:
        if self.__extprogbar is None:
            return
        if threading.current_thread() is not threading.main_thread():
            self.set_extprogbar_inf_sig.emit(fad)
            return
        assert threading.current_thread() is threading.main_thread()
        if fad:
            self.__extprogbar.setStyleSheet(_progbar_style_.get_faded_style(color="green"))
        else:
            self.__extprogbar.setStyleSheet(_progbar_style_.get_unfaded_style(color="green"))
        return

    def activate_extprogbar_logging(self, active:bool, incr_chars:str= '\n') -> None:
        self.__extprogbar_active = active
        self.__progbar_incr_chars = incr_chars
        return

    """
    2. ACCESS EDITOR
    """
    def get_printfunc(self) -> Callable:
        return self.__miniEditor.printout

    def get_printhtmlfunc(self) -> Callable:
        return self.__miniEditor.printout_html

    def printout(self, outputStr:str, color:str="#ffffff") -> None:
        self.__miniEditor.printout(outputStr, color)

    def printout_html(self, outputStr:str, color:str="#ffffff") -> None:
        self.__miniEditor.printout_html(outputStr, color)

    def clear(self) -> None:
        self.__miniEditor.clear()

    def start_progbar(self, title:str) -> None:
        self.__miniEditor.start_progbar(title)
        return

    def set_progbar_val(self, fval:float) -> None:
        self.__miniEditor.set_progbar_val(fval)
        return

    def close_progbar(self) -> None:
        self.__miniEditor.close_progbar()
        return



    """
    3. PROCESS HANDLERS
    """
    def __process_exit_handler__(self, success:bool, code:int) -> None:
        if success:
            assert isinstance(code, int)
            self.printout_html("<br><span style=\"color:#73d216;\">exitCode = {0!s}</span>".format(code))
            return
        errCode = None
        if isinstance(code, int):
            errCode = _pr_.ProcessErr(code)
        else:
            assert isinstance(code, _pr_.ProcessErr)
            errCode = code
        self.printout_html("<br><span style=\"color:#cc0000;\">errCode = {0!s}:{1!s}</span>".format(errCode.value, errCode.name))
        return

    def kill_process(self):
        self.__process.kill_current_process()
        return

    def execute_machine_cmd(self, cmd:str, callback:Callable, callbackArg:object, callbackThread:QThread) -> None:
        '''
        :param cmd:             Command string to execute.
        :param callback:        Callback when process has finished. @param: (success, callbackArg)
        :param callbackArg:     callbackArg=(success, callbackArg)

        '''
        def start(*args):
            if not threading.current_thread() is threading.main_thread():
                _sw_.switch_thread(qthread=_sw_.get_qthread("main"), callback=start, callbackArg=None, notifycaller=nop)
                return
            assert threading.current_thread() is threading.main_thread()
            assert self.__process.is_subprocess_busy() is False
            assert self.__process.is_process_busy() is False
            self.clear_log()
            cwd = os.getcwd().replace('\\', '/')
            self.__miniEditor.printout(f'\n')
            self.__miniEditor.printout(f"{cwd}", "#fce94f")
            self.__miniEditor.printout(f"> ",    "#fce94f")
            self.__miniEditor.printout(f"{cmd}", "#ad7fa8")
            self.__miniEditor.printout(f'\n')
            self.__process.execute_command(command=cmd, subproc_callback=subproc_callback, process_callback=process_callback)
        def subproc_callback():
            print("subprocess callbacks not supported")
            assert False
            return
        def process_callback(success, code):
            if not cmd.startswith("cd "):
                self.__process_exit_handler__(success, code)
            assert not self.__process.processMutex.locked()
            assert not self.__process.subprocessMutex.locked()
            assert self.__process.state() == QProcess.NotRunning
            finish(success, code)
            return
        def finish(success, code):
            process_feedback = (success, code)
            _sw_.switch_thread(qthread=callbackThread, callback=callback, callbackArg=(success, code, callbackArg), notifycaller=nop)
            return
        start()
        return

    def log_output(self, s:str) -> None:
        self.__log__ += s
        if self.__extprogbar_active:
            if self.__progbar_incr_chars in s:
                self.__extprogbar_val += s.count(self.__progbar_incr_chars)
                self.set_extprogbar_val(self.__extprogbar_val)
        return

    def clear_log(self) -> None:
        self.__log__ = ""
        return

    def get_log(self) -> str:
        return self.__log__

    """
    3. FILE OPERATIONS
    """
    def test_write_permissions(self, dirpath:str) -> bool:
        tempfile = _pp_.rel_to_abs(rootpath=dirpath, relpath="temp.txt")
        while os.path.isfile(tempfile):
            tempfile = tempfile[0:-4]
            tempfile += "_.txt"
        assert not os.path.isfile(tempfile)
        try:
            with open(tempfile, 'w+') as f:
                f.write("foo")
        except Exception as e:
            return False
        try:
            _fp_.delete_file(tempfile)
        except Exception as e:
            return False
        return True

    """
    4. BUILD EMBEETLE
    """
    def clean_embeetle(self, beetle_core_dirpath:str,
                             buildtarget_dirpath:str,
                             callback:Callable,
                             callbackArg:object,
                             callbackThread:QThread):
        '''
        Clean build output.

        '''
        assert threading.current_thread() is not threading.main_thread()
        origthread:QThread = QThread.currentThread()
        original_path:str  = None
        def start():
            assert QThread.currentThread() is origthread
            if not os.path.isdir(beetle_core_dirpath):
                self.__miniEditor.printout(f"Cannot find source code directory:\n", "#ef2929")
                self.__miniEditor.printout(f"{beetle_core_dirpath}\n",              "#ffffff")
                finish(False)
                return
            if not os.path.isdir(buildtarget_dirpath):
                self.__miniEditor.printout(f"Cannot find build target directory:\n", "#ef2929")
                self.__miniEditor.printout(f"{buildtarget_dirpath}\n",               "#ffffff")
                finish(False)
                return
            clean()
            return

        def clean(*args):
            assert QThread.currentThread() is origthread
            assert os.path.isdir(buildtarget_dirpath)
            assert os.path.isdir(beetle_core_dirpath)
            # * 1. Clean target directory
            self.__miniEditor.printout("Clean target directory\n", "#fcaf3e")
            self.__miniEditor.printout("======================\n", "#fcaf3e")
            self.set_extprogbar_fad(True)
            self.set_extprogbar_max(0)
            self.activate_extprogbar_logging(False)
            success = _fp_.clean_dir(dir_abspath=buildtarget_dirpath, printfunc=self.__miniEditor.printout, catch_err=True)
            self.__miniEditor.printout('\n')
            if not success:
                finish(False)
                return

            # * 2. Clean zipped folder
            zipfolder = os.path.join(os.path.dirname(buildtarget_dirpath), "embeetle.zip").replace('\\', '/')
            if os.path.isfile(zipfolder):
                self.__miniEditor.printout("Clean zip folder\n", "#fcaf3e")
                self.__miniEditor.printout("================\n", "#fcaf3e")
                success = _fp_.delete_file(file_abspath=zipfolder, printfunc=self.__miniEditor.printout, catch_err=True)
                self.__miniEditor.printout('\n')
                if not success:
                    finish(False)
                    return

            # * 3. Clean 'beetle_updater_windows' or 'beetle_updater_linux'
            beetle_updater_builddir = os.path.join(os.path.dirname(beetle_core_dirpath), f"beetle_updater_{platform.system().lower()}").replace('\\', '/')
            if os.path.exists(beetle_updater_builddir):
                self.__miniEditor.printout(f"Clean beetle_updater_xxx folder\n", "#fcaf3e")
                self.__miniEditor.printout(f"===============================\n", "#fcaf3e")
                success = _fp_.delete_dir(dir_abspath=beetle_updater_builddir, printfunc=self.__miniEditor.printout, catch_err=True)
                self.__miniEditor.printout('\n')
                if not success:
                    finish(False)
                    return

            finish(True)
            return

        def finish(success):
            assert QThread.currentThread() is origthread
            if self.__miniEditor.is_progbar_open():
                print("finish() -> delay")
                QTimer.singleShot(50, functools.partial(finish, success))
                return
            self.set_extprogbar_fad(False)
            self.set_extprogbar_max(100)
            self.set_extprogbar_val(100)
            self.__extprogbar_val = 0
            self.activate_extprogbar_logging(False)
            _sw_.switch_thread(qthread=callbackThread, callback=callback, callbackArg=(success, callbackArg), notifycaller=nop)
            return
        start()
        return


    def build_embeetle(self, beetle_core_dirpath:str,
                             buildtarget_dirpath:str,
                             callback:Callable,
                             callbackArg:object,
                             callbackThread:QThread):
        '''
        Build embeetle locally.

        '''
        assert threading.current_thread() is not threading.main_thread()
        origthread:QThread = QThread.currentThread()
        original_path:str  = None
        def start():
            assert QThread.currentThread() is origthread
            if not os.path.isdir(beetle_core_dirpath):
                self.__miniEditor.printout(f"Cannot find source code directory:\n", "#ef2929")
                self.__miniEditor.printout(f"{beetle_core_dirpath}\n",              "#ffffff")
                finish(False)
                return
            if not os.path.isdir(buildtarget_dirpath):
                s = _fp_.make_dir(dir_abspath=buildtarget_dirpath, printfunc=self.__miniEditor.printout, catch_err=True, overwr=False)
                if not s:
                    self.__miniEditor.printout(f"Cannot create build target directory:\n", "#ef2929")
                    self.__miniEditor.printout(f"{buildtarget_dirpath}\n",                 "#ffffff")
                    finish(False)
                    return
            partial_clean()
            return

        def partial_clean(*args):
            assert QThread.currentThread() is origthread
            assert os.path.isdir(buildtarget_dirpath)
            assert os.path.isdir(beetle_core_dirpath)
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            self.__miniEditor.printout("|                STEP 1: Delete zip folder                  |\n", "#fcaf3e")
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            zipfolder = os.path.join(os.path.dirname(buildtarget_dirpath), "embeetle.zip").replace('\\', '/')
            if os.path.isfile(zipfolder):
                success = _fp_.delete_file(file_abspath=zipfolder, printfunc=self.__miniEditor.printout, catch_err=True)
                self.__miniEditor.printout('\n')
                if not success:
                    finish(False)
                    return
            else:
                self.__miniEditor.printout("No zip folder found.\n")
            self.__miniEditor.printout('\n')
            goto_updaterbuildscript()
            return

        def goto_updaterbuildscript(*args):
            assert QThread.currentThread() is origthread
            assert os.path.isdir(buildtarget_dirpath)
            assert os.path.isdir(beetle_core_dirpath)
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            self.__miniEditor.printout("|               STEP 2: GO TO 'beetle_updater_src'          |\n", "#fcaf3e")
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            nonlocal original_path
            original_path = os.getcwd().replace('\\', '/')
            beetle_updater_srcdir = os.path.join(os.path.dirname(beetle_core_dirpath), f"beetle_updater_src").replace('\\', '/')
            cmd = f"cd \"{beetle_updater_srcdir}\""
            self.execute_machine_cmd(cmd=cmd, callback=freeze_updater, callbackArg=None, callbackThread=origthread)
            return

        def freeze_updater(arg):
            assert QThread.currentThread() is origthread
            success, code, _ = arg
            if not success:
                finish(False)
                return
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            self.__miniEditor.printout("|                 STEP 3: FREEZE THE UPDATER                |\n", "#fcaf3e")
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            python = "python" if platform.system().lower() == "windows" else "python3"
            cmd = f"{python} build.py"
            self.execute_machine_cmd(cmd=cmd, callback=goto_buildscript, callbackArg=None, callbackThread=origthread)
            return

        def goto_buildscript(arg):
            assert QThread.currentThread() is origthread
            success, code, _ = arg
            if not success:
                finish(False)
                return
            assert os.path.isdir(buildtarget_dirpath)
            assert os.path.isdir(beetle_core_dirpath)
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            self.__miniEditor.printout("|             STEP 4: GO TO 'beetle_core/to_exe'            |\n", "#fcaf3e")
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            nonlocal original_path
            original_path = os.getcwd().replace('\\', '/')
            to_exe_dirpath = os.path.join(beetle_core_dirpath, "to_exe").replace('\\', '/')
            cmd = f"cd \"{to_exe_dirpath}\""
            self.execute_machine_cmd(cmd=cmd, callback=compute_freeze_nr, callbackArg=None, callbackThread=origthread)
            return

        def compute_freeze_nr(arg):
            assert QThread.currentThread() is origthread
            success, code, _ = arg
            if not success:
                finish(False)
                return
            def parse_freeze_nr(arg):
                assert QThread.currentThread() is origthread
                success, code, _ = arg
                if not success:
                    finish(False)
                    return
                try:
                    p = re.compile(r"(Number of files to be compiled:)\s*(\d+)", re.MULTILINE)
                    match = p.search(self.get_log())
                    n = int(match.group(2))
                    freeze_embeetle(n)
                    return
                except Exception as e:
                    finish(False)
                    return
                return
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            self.__miniEditor.printout("|                  STEP 5: FREEZE EMBEETLE                  |\n", "#fcaf3e")
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            python = "python" if platform.system().lower() == "windows" else "python3"
            cmd = f"{python} freeze_embeetle.py --output \"{buildtarget_dirpath}\" --info-only"
            self.execute_machine_cmd(cmd=cmd, callback=parse_freeze_nr, callbackArg=None, callbackThread=origthread)
            return
        def freeze_embeetle(n):
            assert QThread.currentThread() is origthread
            self.__miniEditor.printout('\n')
            # * Activate progbar
            self.set_extprogbar_fad(False)
            self.set_extprogbar_max(n)
            self.activate_extprogbar_logging(True, "running build_ext")
            python = "python" if platform.system().lower() == "windows" else "python3"
            cmd = f"{python} freeze_embeetle.py --output \"{buildtarget_dirpath}\""
            self.execute_machine_cmd(cmd=cmd, callback=delete_cfiles, callbackArg=None, callbackThread=origthread)
            return

        def delete_cfiles(arg):
            assert QThread.currentThread() is origthread
            success, code, _ = arg
            if not success:
                finish(False)
                return
            self.set_extprogbar_fad(True)
            self.set_extprogbar_max(0)
            self.activate_extprogbar_logging(False)
            beetle_core_dst = os.path.join(buildtarget_dirpath, "beetle_core").replace('\\', '/')
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            self.__miniEditor.printout("|        STEP 6: DELETE ALL C-FILES FROM 'beetle_core'      |\n", "#fcaf3e")
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            for root, dirs, files in os.walk(beetle_core_dst):
                for name in files:
                    if name.endswith('.c'):
                        abspath = os.path.join(root, name).replace('\\', '/')
                        success = _fp_.delete_file(file_abspath=abspath, printfunc=self.__miniEditor.printout, catch_err=True)
                        if not success:
                            finish(False)
                            return
            self.__miniEditor.printout('...done\n')
            copy_tools()
            return

        def copy_tools():
            assert QThread.currentThread() is origthread
            self.__miniEditor.printout('\n\n')
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            self.__miniEditor.printout("|                  STEP 7: COPY 'beetle_tools'              |\n", "#fcaf3e")
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            beetle_tools_src = os.path.join(os.path.dirname(beetle_core_dirpath), "beetle_tools").replace('\\', '/')
            beetle_tools_dst = os.path.join(buildtarget_dirpath, "beetle_tools").replace('\\', '/')
            if not os.path.isdir(beetle_tools_dst):
                self.copy_folder(sourcedir_abspath = beetle_tools_src,
                                 targetdir_abspath = beetle_tools_dst,
                                 exclusions        = ["Linux", ] if platform.system().lower() == "windows" else ["Windows", ],
                                 show_prog         = True,
                                 delsource         = False,
                                 callback          = copy_resources,
                                 callbackArg       = None,
                                 callbackThread    = origthread)
            else:
                assert os.path.isdir(beetle_tools_dst)
                beetle_tools_src += '/'
                beetle_tools_dst += '/'
                self.rsync_local(src_dirpath    = beetle_tools_src,
                                 tgt_dirpath    = beetle_tools_dst,
                                 exclusions     = ["Linux", ] if platform.system().lower() == "windows" else ["Windows", ],
                                 callback       = copy_resources,
                                 callbackArg    = None,
                                 callbackThread = origthread)
            return

        def copy_resources(arg):
            assert QThread.currentThread() is origthread
            if self.__miniEditor.is_progbar_open():
                print("copy_resources() -> delay")
                QTimer.singleShot(50, functools.partial(copy_resources, arg))
                return
            success, _ = arg
            if not success:
                finish(False)
                return
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            self.__miniEditor.printout("|              STEP 8: COPY 'beetle_core/resources'         |\n", "#fcaf3e")
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            resources_src = os.path.join(beetle_core_dirpath, "resources").replace('\\', '/')
            resources_dst = os.path.join(buildtarget_dirpath, "beetle_core/resources").replace('\\', '/')
            if not os.path.isdir(resources_dst):
                self.copy_folder(sourcedir_abspath = resources_src,
                                 targetdir_abspath = resources_dst,
                                 exclusions        = ["inkscape_resources", "web_figures", '*.svg', ],
                                 show_prog         = True,
                                 delsource         = False,
                                 callback          = copy_updater,
                                 callbackArg       = None,
                                 callbackThread    = origthread)
            else:
                assert os.path.isdir(resources_dst)
                resources_src += '/'
                resources_dst += '/'
                self.rsync_local(src_dirpath    = resources_src,
                                 tgt_dirpath    = resources_dst,
                                 exclusions     = ["inkscape_resources", "web_figures", '*.svg', ],
                                 callback       = copy_updater,
                                 callbackArg    = None,
                                 callbackThread = origthread)
            return

        def copy_updater(arg):
            assert QThread.currentThread() is origthread
            if self.__miniEditor.is_progbar_open():
                print("copy_updater() -> delay")
                QTimer.singleShot(50, functools.partial(copy_updater, arg))
                return
            success, _ = arg
            if not success:
                finish(False)
                return
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            self.__miniEditor.printout("|               STEP 9: COPY 'beetle_updater_xxx'           |\n", "#fcaf3e")
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            beetle_updater_src = os.path.join(os.path.dirname(beetle_core_dirpath), f"beetle_updater_{platform.system().lower()}").replace('\\', '/')
            beetle_updater_dst = os.path.join(buildtarget_dirpath, f"beetle_updater_{platform.system().lower()}").replace('\\', '/')
            if not os.path.isdir(beetle_updater_dst):
                self.copy_folder(sourcedir_abspath = beetle_updater_src,
                                 targetdir_abspath = beetle_updater_dst,
                                 exclusions        = None,
                                 show_prog         = True,
                                 delsource         = False,
                                 callback          = copy_licenses,
                                 callbackArg       = None,
                                 callbackThread    = origthread)
            else:
                assert os.path.isdir(beetle_updater_dst)
                beetle_updater_src += '/'
                beetle_updater_dst += '/'
                self.rsync_local(src_dirpath    = beetle_updater_src,
                                 tgt_dirpath    = beetle_updater_dst,
                                 exclusions     = None,
                                 callback       = copy_licenses,
                                 callbackArg    = None,
                                 callbackThread = origthread)
            return

        def copy_licenses(arg):
            assert QThread.currentThread() is origthread
            if self.__miniEditor.is_progbar_open():
                print("copy_licenses() -> delay")
                QTimer.singleShot(50, functools.partial(copy_licenses, arg))
                return
            success, _ = arg
            if not success:
                finish(False)
                return
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            self.__miniEditor.printout("|                    STEP 10: COPY 'licenses'               |\n", "#fcaf3e")
            self.__miniEditor.printout("|===========================================================|\n", "#fcaf3e")
            licenses_src = os.path.join(os.path.dirname(beetle_core_dirpath), "licenses").replace('\\', '/')
            licenses_dst = os.path.join(buildtarget_dirpath, "licenses").replace('\\', '/')
            if not os.path.isdir(licenses_dst):
                self.copy_folder(sourcedir_abspath = licenses_src,
                                 targetdir_abspath = licenses_dst,
                                 exclusions        = None,
                                 show_prog         = True,
                                 delsource         = False,
                                 callback          = finish,
                                 callbackArg       = None,
                                 callbackThread    = origthread)
            else:
                assert os.path.isdir(licenses_dst)
                licenses_src += '/'
                licenses_dst += '/'
                self.rsync_local(src_dirpath    = licenses_src,
                                 tgt_dirpath    = licenses_dst,
                                 exclusions     = None,
                                 callback       = finish,
                                 callbackArg    = None,
                                 callbackThread = origthread)
            return

        def finish(arg):
            assert QThread.currentThread() is origthread
            if self.__miniEditor.is_progbar_open():
                print("finish() -> delay")
                QTimer.singleShot(50, functools.partial(finish, arg))
                return
            success = False
            if isinstance(arg, bool):
                success = arg
            else:
                success, _ = arg
            self.set_extprogbar_fad(False)
            self.set_extprogbar_max(100)
            self.set_extprogbar_val(100)
            self.__extprogbar_val = 0
            self.activate_extprogbar_logging(False)
            _sw_.switch_thread(qthread=callbackThread, callback=callback, callbackArg=(success, callbackArg), notifycaller=nop)
            return
        start()
        return

    def zip_embeetle(self, beetle_core_dirpath:str,
                           buildtarget_dirpath:str,
                           callback:Callable,
                           callbackArg:object,
                           callbackThread:QThread):
        '''
        Zip embeetle locally.

        '''
        assert threading.current_thread() is not threading.main_thread()
        origthread:QThread = QThread.currentThread()
        original_path:str  = None
        def start():
            assert QThread.currentThread() is origthread
            if not os.path.isdir(beetle_core_dirpath):
                self.__miniEditor.printout(f"Cannot find source code directory:\n", "#ef2929")
                self.__miniEditor.printout(f"{beetle_core_dirpath}\n",              "#ffffff")
                finish(False)
                return
            if not os.path.isdir(buildtarget_dirpath):
                self.__miniEditor.printout(f"Cannot find build target directory:\n", "#ef2929")
                self.__miniEditor.printout(f"{buildtarget_dirpath}\n",               "#ffffff")
                finish(False)
                return
            zip_folder()
            return

        def zip_folder():
            assert QThread.currentThread() is origthread
            if self.__miniEditor.is_progbar_open():
                print("zip_folder() -> delay")
                QTimer.singleShot(50, zip_folder)
                return
            print("zip_folder() -> execute")
            self.set_extprogbar_fad(True)
            self.set_extprogbar_max(0)
            self.activate_extprogbar_logging(False)
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("STEP 1: Zip folder\n", "#fcaf3e")
            self.__miniEditor.printout("------------------\n", "#fcaf3e")
            # copied_embeetle_dirpath = os.path.join(buildtarget_dirpath, "copied_embeetle").replace('\\', '/')
            # compiled_files_txt      = os.path.join(buildtarget_dirpath, "compiled_files.txt").replace('\\', '/')
            zipped_folderpath       = os.path.join(os.path.dirname(buildtarget_dirpath), "embeetle.zip").replace('\\', '/')
            self.zip_dir_to_file(sourcedir_abspath  = buildtarget_dirpath,
                                 targetfile_abspath = zipped_folderpath,
                                 forbidden_dirnames = ["copied_embeetle", ],
                                 forbidden_filenames= ["compiled_files.txt", ],
                                 show_prog          = True,
                                 callback           = finish,
                                 callbackArg        = None,
                                 callbackThread     = origthread)
            return

        def finish(arg):
            assert QThread.currentThread() is origthread
            if self.__miniEditor.is_progbar_open():
                print("finish() -> delay")
                QTimer.singleShot(50, functools.partial(finish, arg))
                return
            success = False
            if isinstance(arg, bool):
                success = arg
            else:
                success, _ = arg
            self.set_extprogbar_fad(False)
            self.set_extprogbar_max(100)
            self.set_extprogbar_val(100)
            self.__extprogbar_val = 0
            self.activate_extprogbar_logging(False)
            _sw_.switch_thread(qthread=callbackThread, callback=callback, callbackArg=(success, callbackArg), notifycaller=nop)
            return
        start()
        return

    def __get_nr_transfers__(self, src_dirpath:str,
                                   tgt_dirpath:str,
                                   exclusions:List[str],
                                   callback:Callable,
                                   callbackArg:object):
        '''
        Run rsync in dry-run mode to acquire the nr of transfers (file + directory).
            Attention: The `src_dirpath` must already be equal to the cwd.
                       This function won't change the cwd.

        '''
        assert threading.current_thread() is not threading.main_thread()
        origthread: QThread = QThread.currentThread()
        rsync_folder = _pp_.rel_to_abs(rootpath=data.tools_directory, relpath=f"{platform.system()}/rsync")
        rsyncpath    = _pp_.rel_to_abs(rootpath=rsync_folder, relpath="rsync.exe")
        def start():
            assert QThread.currentThread() is origthread
            assert os.getcwd().replace('\\', '/')       == src_dirpath.replace('\\', '/') or \
                   os.getcwd().replace('\\', '/')[0:-1] == src_dirpath.replace('\\', '/') or \
                   os.getcwd().replace('\\', '/')       == src_dirpath.replace('\\', '/')[0:-1]
            run_rsync()
            return
        def run_rsync():
            assert QThread.currentThread() is origthread
            nonlocal tgt_dirpath
            if tgt_dirpath.startswith("C:"):
                tgt_dirpath = tgt_dirpath.replace("C:", "/cygdrive/c")
            if tgt_dirpath.startswith("D:"):
                tgt_dirpath = tgt_dirpath.replace("D:", "/cygdrive/c")
            exclusions_str = ''
            if exclusions is not None:
                exclusions_str = "--exclude " + " --exclude ".join(f"'{e}'" for e in exclusions) + " --delete-excluded"
            cmd = f"\"{rsyncpath}\" -av --delete {exclusions_str} --dry-run --stats ./ {tgt_dirpath}"
            self.execute_machine_cmd(cmd=cmd, callback=process_rsync_output, callbackArg=None, callbackThread=origthread)
            return
        def process_rsync_output(arg):
            assert QThread.currentThread() is origthread
            success, code, _ = arg
            n = -1
            if (success == False) or (code != 0):
                finish(-1)
                return
            try:
                p = re.compile(r"(Number of created files:)\s*([\d,]+)", re.MULTILINE)
                match = p.search(self.get_log())
                n1 = int(match.group(2).replace(',', ''))
                p = re.compile(r"(Number of deleted files:)\s*([\d,]+)", re.MULTILINE)
                match = p.search(self.get_log())
                n2 = int(match.group(2).replace(',', ''))
                n = n1 + n2
            except Exception as e:
                finish(-1)
                return
            finish(n)
            return
        def finish(n):
            assert QThread.currentThread() is origthread
            callback(n, callbackArg)
            return
        start()
        return

    def __get_nr_remote_transfers__(self, remote_username:str,
                                          remote_domain:str,
                                          remote_dirpath:str,
                                          local_dirpath:str,
                                          exclusions:List[str],
                                          known_hosts_tempfilepath:str,
                                          client_id_rsa_tempfilepath:str,
                                          reverse:bool,
                                          local_keypath:str,
                                          callback:Callable,
                                          callbackArg:object):
        '''
        Run rsync in dry-run mode to acquire the nr of transfers (file + directory).
            Attention: The `local_dirpath` must already be equal to the cwd.
                       This function won't change the cwd.

        '''
        assert threading.current_thread() is not threading.main_thread()
        if reverse:
            assert client_id_rsa_tempfilepath is None
            assert local_keypath is not None
        else:
            assert client_id_rsa_tempfilepath is not None
            assert local_keypath is None
        origthread:QThread = QThread.currentThread()
        original_path = None
        rsync_folder  = _pp_.rel_to_abs(rootpath=data.tools_directory, relpath=f"{platform.system()}/rsync")
        rsyncpath     = _pp_.rel_to_abs(rootpath=rsync_folder, relpath="rsync.exe")
        if platform.system() == "Windows":
            sshpath = _pp_.rel_to_abs(rootpath=rsync_folder, relpath="ssh.exe")
        else:
            sshpath = "ssh"
        def start():
            assert QThread.currentThread() is origthread
            assert os.getcwd().replace('\\', '/')       == local_dirpath.replace('\\', '/') or \
                   os.getcwd().replace('\\', '/')[0:-1] == local_dirpath.replace('\\', '/') or \
                   os.getcwd().replace('\\', '/')       == local_dirpath.replace('\\', '/')[0:-1]
            run_rsync()
            return
        def run_rsync():
            assert QThread.currentThread() is origthread
            exclusions_str = ''
            if exclusions is not None:
                exclusions_str = "--exclude " + " --exclude ".join(f"'{e}'" for e in exclusions) + " --delete-excluded"
            if not reverse:
                cmd = f"\"{rsyncpath}\" -av --delete {exclusions_str} --dry-run --stats -e \"'{sshpath}' -i '{client_id_rsa_tempfilepath}' -o UserKnownHostsFile='{known_hosts_tempfilepath}'\" {remote_username}@{remote_domain}:{remote_dirpath} ./"
            else:
                cmd = f"\"{rsyncpath}\" -av --delete {exclusions_str} --dry-run --stats -e \"'{sshpath}' -i '{local_keypath}' -o UserKnownHostsFile='{known_hosts_tempfilepath}'\" ./ {remote_username}@{remote_domain}:{remote_dirpath}"
            self.execute_machine_cmd(cmd=cmd, callback=process_rsync_output, callbackArg=None, callbackThread=origthread)
            return
        def process_rsync_output(arg):
            assert QThread.currentThread() is origthread
            success, code, _ = arg
            n = -1
            if (success == False) or (code != 0):
                finish(-1)
                return
            try:
                p = re.compile(r"(Number of created files:)\s*([\d,]+)", re.MULTILINE)
                match = p.search(self.get_log())
                n1 = int(match.group(2).replace(',', ''))
                p = re.compile(r"(Number of deleted files:)\s*([\d,]+)", re.MULTILINE)
                match = p.search(self.get_log())
                n2 = int(match.group(2).replace(',', ''))
                n = n1 + n2
            except Exception as e:
                finish(-1)
                return
            finish(n)
            return
        def finish(n):
            assert QThread.currentThread() is origthread
            callback(n, callbackArg)
            return
        start()
        return

    def rsync_local(self, src_dirpath:str,
                          tgt_dirpath:str,
                          exclusions:List[str],
                          callback:Callable,
                          callbackArg:object,
                          callbackThread: QThread):
        '''

        :param src_dirpath:
        :param tgt_dirpath:
        :param callback:
        :param callbackArg:
        :param callbackThread:
        :return:
        '''
        assert threading.current_thread() is not threading.main_thread()
        origthread:QThread = QThread.currentThread()
        original_path = None
        rsync_folder  = _pp_.rel_to_abs(rootpath=data.tools_directory, relpath=f"{platform.system()}/rsync")
        rsyncpath     = _pp_.rel_to_abs(rootpath=rsync_folder, relpath="rsync.exe")
        progbar_value = 0
        def start():
            assert QThread.currentThread() is origthread
            nonlocal original_path
            self.__miniEditor.printout("STEP 1: Go to source directory\n", "#fcaf3e")
            self.__miniEditor.printout("------------------------------", "#fcaf3e")
            original_path = os.getcwd().replace('\\', '/')
            cmd = f"cd \"{src_dirpath}\""
            self.execute_machine_cmd(cmd=cmd, callback=get_nr_transfers, callbackArg=None, callbackThread=origthread)
            return
        def get_nr_transfers(arg):
            assert QThread.currentThread() is origthread
            success, code, _ = arg
            if (success == False) or (code != 0):
                finish(False)
                return
            self.__miniEditor.printout("STEP 2: Rsync dry-run: get nr of transfers\n", "#fcaf3e")
            self.__miniEditor.printout("------------------------------------------", "#fcaf3e")
            self.set_extprogbar_fad(True)
            self.set_extprogbar_max(0)
            self.__get_nr_transfers__(src_dirpath=src_dirpath,
                                      tgt_dirpath=tgt_dirpath,
                                      exclusions=exclusions,
                                      callback=run_rsync,
                                      callbackArg=None)
            return
        def run_rsync(n, *args):
            assert QThread.currentThread() is origthread
            nonlocal tgt_dirpath
            if n == -1:
                finish(False)
                return
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("STEP 3: Rsync run\n", "#fcaf3e")
            self.__miniEditor.printout("-----------------", "#fcaf3e")
            if n != 0:
                self.set_extprogbar_fad(False)
                self.set_extprogbar_max(n)
                self.activate_extprogbar_logging(True)
            if tgt_dirpath.startswith("C:"):
                tgt_dirpath = tgt_dirpath.replace("C:", "/cygdrive/c")
            if tgt_dirpath.startswith("D:"):
                tgt_dirpath = tgt_dirpath.replace("D:", "/cygdrive/d")
            exclusions_str = ''
            if exclusions is not None:
                exclusions_str = "--exclude " + " --exclude ".join(f"'{e}'" for e in exclusions) + " --delete-excluded"
            cmd = f"\"{rsyncpath}\" -av --delete {exclusions_str} ./ {tgt_dirpath}"
            self.execute_machine_cmd(cmd=cmd, callback=restore_cwd, callbackArg=None, callbackThread=origthread)
            return
        def restore_cwd(arg):
            assert QThread.currentThread() is origthread
            success, code, _ = arg
            if (success == False) or (code != 0):
                finish(False)
                return
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("STEP 4: Return to original path\n", "#fcaf3e")
            self.__miniEditor.printout("-------------------------------", "#fcaf3e")
            cmd = f"cd \"{original_path}\""
            self.execute_machine_cmd(cmd=cmd, callback=finish, callbackArg=success, callbackThread=origthread)
            return
        def finish(arg):
            assert QThread.currentThread() is origthread
            success = None
            if isinstance(arg, bool):
                success = arg
            else:
                success, code, _ = arg
                if code != 0:
                    success = False
            self.set_extprogbar_fad(False)
            self.set_extprogbar_max(100)
            self.set_extprogbar_val(100)
            self.__extprogbar_val = 0
            self.activate_extprogbar_logging(False)
            assert QThread.currentThread() is origthread
            _sw_.switch_thread(qthread=callbackThread, callback=callback, callbackArg=(success, callbackArg), notifycaller=nop)
            return
        start()
        return


    def rsync_server_to_local(self, remote_username:str,
                                    remote_domain:str,
                                    remote_dirpath:str,
                                    local_dirpath:str,
                                    exclusions:List[str],
                                    known_hosts_url:str,
                                    client_id_rsa_url:str,
                                    reverse:bool,
                                    local_keypath:str,
                                    callback:Callable,
                                    callbackArg:object,
                                    callbackThread:QThread):
        '''
        Apply the rsync command:
            rsync -av remote_username@remote_domain:remote_dirpath local_dirpath

        :param remote_username:     Username at remote server.
        :param remote_domain:       Domain name of server.
        :param remote_dirpath:      Absolute directory path on server.
        :param local_dirpath:       Absolute directory path on local computer.
        :param known_hosts_url:     URL to 'known_hosts' file.
        :param client_id_rsa_url:   URL to 'client_id_rsa' file. Only needed for downstream.
        :param reverse:             Upstream sync.
        :param local_keypath:       Location of local key. Only needed for upstream.

        :param callback:            Callback when rsync has finished. @param: (success, callbackArg)
        :param callbackArg:         callbackArg=(success, callbackArg)
        :param callbackThread:      QThread you want the callback to run in.

        '''
        assert threading.current_thread() is not threading.main_thread()
        if reverse:
            assert client_id_rsa_url is None
            assert local_keypath is not None
            assert os.path.isfile(local_keypath)
        else:
            assert client_id_rsa_url is not None
            assert local_keypath is None
        origthread:QThread = QThread.currentThread()
        original_path = None
        rsync_folder               = _pp_.rel_to_abs(rootpath=data.tools_directory, relpath=f"{platform.system()}/rsync")
        rsyncpath                  = _pp_.rel_to_abs(rootpath=rsync_folder, relpath="rsync.exe")
        if platform.system() == "Windows":
            sshpath = _pp_.rel_to_abs(rootpath=rsync_folder, relpath="ssh.exe")
        else:
            sshpath = "ssh"
        known_hosts_tempfilepath   = None
        client_id_rsa_tempfilepath = None
        def start():
            assert QThread.currentThread() is origthread
            nonlocal original_path
            self.__miniEditor.printout("STEP 1: Go to local directory\n", "#fcaf3e")
            self.__miniEditor.printout("------------------------------", "#fcaf3e")
            original_path = os.getcwd().replace('\\', '/')
            cmd = f"cd \"{local_dirpath}\""
            self.execute_machine_cmd(cmd=cmd, callback=download_keys, callbackArg=None, callbackThread=origthread)
            return
        def download_keys(arg):
            assert QThread.currentThread() is origthread
            success, code, _ = arg
            if (success == False) or (code != 0):
                finish(False)
                return
            self.__miniEditor.printout("STEP 2: Download ssh keys\n", "#fcaf3e")
            self.__miniEditor.printout("-------------------------\n", "#fcaf3e")
            def download_known_hosts(*args):
                assert QThread.currentThread() is origthread
                self.download_file(url=known_hosts_url, show_prog=True, callback=download_client_id_rsa, callbackArg=None, callbackThread=origthread)
                return
            def download_client_id_rsa(*args):
                assert QThread.currentThread() is origthread
                success, filepath, _ = args[0]
                if not success:
                    finish(False)
                    return
                nonlocal known_hosts_tempfilepath
                known_hosts_tempfilepath = filepath
                if reverse:
                    self.__miniEditor.printout(f"Upstream mode ->             \n")
                    self.__miniEditor.printout(f"No need to download rsa file.\n")
                    self.__miniEditor.printout(f"Use local key instead:       \n")
                    self.__miniEditor.printout(f"    {local_keypath}\n\n")
                    finish_downloads((True, None, None))
                else:
                    print(f"Download file: {client_id_rsa_url}")
                    self.download_file(url=client_id_rsa_url, show_prog=True, callback=finish_downloads, callbackArg=None, callbackThread=origthread)
                return
            def finish_downloads(*args):
                assert QThread.currentThread() is origthread
                success, filepath, _ = args[0]
                if not reverse:
                    print(f"Downloaded {client_id_rsa_url} to {filepath}")
                if (success != True) or ((reverse == False) and (filepath is None)):
                    finish(False)
                    return
                nonlocal client_id_rsa_tempfilepath
                client_id_rsa_tempfilepath = filepath
                get_nr_transfers()
                return
            download_known_hosts()
            return
        def get_nr_transfers():
            assert QThread.currentThread() is origthread
            self.__miniEditor.printout("STEP 3: Rsync dry-run: get nr of transfers\n", "#fcaf3e")
            self.__miniEditor.printout("------------------------------------------", "#fcaf3e")
            self.set_extprogbar_fad(True)
            self.set_extprogbar_max(0)
            self.__get_nr_remote_transfers__(remote_username=remote_username,
                                             remote_domain=remote_domain,
                                             remote_dirpath=remote_dirpath,
                                             local_dirpath=local_dirpath,
                                             exclusions=exclusions,
                                             known_hosts_tempfilepath=known_hosts_tempfilepath,
                                             client_id_rsa_tempfilepath=client_id_rsa_tempfilepath,
                                             reverse=reverse,
                                             local_keypath=local_keypath,
                                             callback=run_rsync,
                                             callbackArg=None)
            return
        def run_rsync(n, *args):
            assert QThread.currentThread() is origthread
            if n == -1:
                finish(False)
                return
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("STEP 4: Rsync run\n", "#fcaf3e")
            self.__miniEditor.printout("-----------------", "#fcaf3e")
            if n != 0:
                self.set_extprogbar_fad(False)
                self.set_extprogbar_max(n)
                self.activate_extprogbar_logging(True)
            exclusions_str = ''
            if exclusions is not None:
                exclusions_str = "--exclude " + " --exclude ".join(f"'{e}'" for e in exclusions) + " --delete-excluded"
            if not reverse:
                cmd = f"\"{rsyncpath}\" -av --delete {exclusions_str} -e \"'{sshpath}' -i '{client_id_rsa_tempfilepath}' -o UserKnownHostsFile='{known_hosts_tempfilepath}'\" {remote_username}@{remote_domain}:{remote_dirpath} ./"
            else:
                cmd = f"\"{rsyncpath}\" -av --delete {exclusions_str} -e \"'{sshpath}' -i '{local_keypath}' -o UserKnownHostsFile='{known_hosts_tempfilepath}'\" ./ {remote_username}@{remote_domain}:{remote_dirpath}"
            self.execute_machine_cmd(cmd=cmd, callback=restore_cwd, callbackArg=None, callbackThread=origthread)
            return
        def restore_cwd(arg):
            assert QThread.currentThread() is origthread
            success, code, _ = arg
            if (success == False) or (code != 0):
                finish(False)
                return
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout('\n')
            self.__miniEditor.printout("STEP 5: Return to original path\n", "#fcaf3e")
            self.__miniEditor.printout("-------------------------------", "#fcaf3e")
            cmd = f"cd \"{original_path}\""
            self.execute_machine_cmd(cmd=cmd, callback=finish, callbackArg=success, callbackThread=origthread)
            return
        def finish(arg):
            assert QThread.currentThread() is origthread
            success = None
            if isinstance(arg, bool):
                success = arg
            else:
                success, code, _ = arg
                if code != 0:
                    success = False
            self.set_extprogbar_fad(False)
            self.set_extprogbar_max(100)
            self.set_extprogbar_val(100)
            self.__extprogbar_val = 0
            self.activate_extprogbar_logging(False)
            assert QThread.currentThread() is origthread
            _sw_.switch_thread(qthread=callbackThread, callback=callback, callbackArg=(success, callbackArg), notifycaller=nop)
            return
        start()
        return

    def copy_folder(self, sourcedir_abspath:str,
                          targetdir_abspath:str,
                          exclusions:List[str],
                          show_prog:bool,
                          delsource:bool,
                          callback:Callable,
                          callbackArg:object,
                          callbackThread:QThread) -> None:
        '''
        Copy a big folder from the given 'sourcedir_abspath' to 'targetdir_abspath'. If the target directory already
        exists, it will be cleaned first.

        :param sourcedir_abspath:   Source directory.
        :param targetdir_abspath:   Target directory.
        :param show_prog:           Show a progressbar.
        :param delsource:           Perform a move instead of a copy.
        :param callback:            Provide a callback.
        :param callbackArg:         callbackArg=(success, callbackArg)
        :param callbackThread:      QThread you want the callback to run in.

        '''
        assert threading.current_thread() is not threading.main_thread()
        origthread = QThread.currentThread()
        def start():
            QTimer.singleShot(50, dircopy)
            return
        def dircopy(*args):
            j: int    = 0    # Cntr on reporthook calls.
            jmax: int = 1    # Max for cntr, reporthook should update progressbar on overflow.
            def reporthook(i, n):
                nonlocal j, jmax
                j += 1
                if j > jmax:
                    j = 0
                    jmax = int( n / 100.0)  # Calculate 'jmax' such that cntr overflow happens 100 times.
                    perc = 100.0 * (i / n)
                    if show_prog:
                        if not self.__miniEditor.is_progbar_open():
                            if delsource:
                                self.start_progbar("Move:")
                            else:
                                self.start_progbar("Copy:")
                        self.set_progbar_val(perc)
                return

            if delsource:
                success = _fp_.move_dir(sourcedir_abspath=sourcedir_abspath,
                                        targetdir_abspath=targetdir_abspath,
                                        exclusions=exclusions,
                                        reporthook=reporthook,
                                        printfunc=self.get_printfunc(),
                                        catch_err=True,
                                        overwr=True)
            else:
                success = _fp_.copy_dir(sourcedir_abspath=sourcedir_abspath,
                                        targetdir_abspath=targetdir_abspath,
                                        exclusions=exclusions,
                                        reporthook=reporthook,
                                        printfunc=self.get_printfunc(),
                                        catch_err=True,
                                        overwr=True)
            if show_prog and self.__miniEditor.is_progbar_open():
                self.set_progbar_val(100.0)
                self.close_progbar()
            self.__miniEditor.printout('\n')
            if not success:
                finish(False)
                return
            QTimer.singleShot(100, lambda: finish(True))
            return
        def finish(success):
            assert QThread.currentThread() is origthread
            if self.__miniEditor.is_progbar_open():
                print(f"WARNING: copy_folder({targetdir_abspath.split('/')[-1]}) did not properly close the progbar!")
                self.close_progbar()
                QTimer.singleShot(250, functools.partial(finish, success))
                return
            self.__miniEditor.printout('\n')
            _sw_.switch_thread(qthread=callbackThread, callback=callback, callbackArg=(success, callbackArg), notifycaller=nop)
            return
        start()
        return

    def zip_dir_to_file(self, sourcedir_abspath:str, targetfile_abspath:str, forbidden_dirnames:List[str], forbidden_filenames:List[str], show_prog:bool, callback:Callable, callbackArg:object, callbackThread:QThread) -> None:
        '''
        Zip the given folder into a .zip file.

        :param sourcedir_abspath:   Folder getting zipped. Must exist.
        :param targetfile_abspath:  Target .zip file. If exists, gets deleted first.
        :param show_prog:           Show a progressbar.
        :param callback:            Provide a callback.
        :param callbackArg:         callbackArg=(success, callbackArg)
        :param callbackThread:      QThread you want the callback to run in.
        '''
        assert threading.current_thread() is not threading.main_thread()
        origthread = QThread.currentThread()
        def start():
            QTimer.singleShot(50, dirzip)
            return
        def dirzip(*args):
            j: int    = 0    # Cntr on reporthook calls.
            jmax: int = 1    # Max for cntr, reporthook should update progressbar on overflow.
            def reporthook(i, n):
                nonlocal j, jmax
                j += 1
                if j > jmax:
                    j = 0
                    jmax = int( n / 100.0)  # Calculate 'jmax' such that cntr overflow happens 100 times.
                    perc = 100.0 * (i / n)
                    if show_prog:
                        if not self.__miniEditor.is_progbar_open():
                            self.start_progbar("Zip:")
                        self.set_progbar_val(perc)
                return

            success = _fp_.zip_dir_to_file(sourcedir_abspath=sourcedir_abspath,
                                           targetfile_abspath=targetfile_abspath,
                                           forbidden_dirnames=forbidden_dirnames,
                                           forbidden_filenames=forbidden_filenames,
                                           reporthook=reporthook,
                                           printfunc=self.get_printfunc(),
                                           catch_err=True,
                                           overwr=True)
            if show_prog and self.__miniEditor.is_progbar_open():
                self.set_progbar_val(100.0)
                self.close_progbar()
            self.__miniEditor.printout('\n')
            if not success:
                finish(False)
                return
            QTimer.singleShot(50, lambda: finish(True))
            return
        def finish(success):
            assert QThread.currentThread() is origthread
            _sw_.switch_thread(qthread=callbackThread, callback=callback, callbackArg=(success, callbackArg), notifycaller=nop)
            return
        start()
        return

    def unzip_file_to_dir(self, spath:str, dpath:str, show_prog:bool, callback:Callable, callbackArg:object, callbackThread:QThread) -> None:
        '''
        Unzip the given file to its original directory.

        :param spath:
        :param dpath:
        :param callback:
        :param callbackArg:
        :param callbackThread:
        :return:
        '''
        assert threading.current_thread() is not threading.main_thread()
        origthread = QThread.currentThread()
        def start():
            QTimer.singleShot(50, dirunzip)
            return
        def dirunzip(*args):
            j: int    = 0    # Cntr on reporthook calls.
            jmax: int = 1    # Max for cntr, reporthook should update progressbar on overflow.
            def reporthook(i, n):
                nonlocal j, jmax
                j += 1
                if j > jmax:
                    j = 0
                    jmax = int( n / 100.0)  # Calculate 'jmax' such that cntr overflow happens 100 times.
                    perc = 100.0 * (i / n)
                    if show_prog:
                        if not self.__miniEditor.is_progbar_open():
                            self.start_progbar("Unzip:")
                        self.set_progbar_val(perc)
                return

            success = _fp_.unzip_file_to_dir(sourcefile_abspath=spath, targetdir_abspath=dpath,
                                             reporthook=reporthook, printfunc=self.get_printfunc(), catch_err=True, overwr=True)
            if show_prog and self.__miniEditor.is_progbar_open():
                self.set_progbar_val(100.0)
                self.close_progbar()
            self.__miniEditor.printout('\n')
            if not success:
                finish(False)
                return
            QTimer.singleShot(50, lambda: finish(True))
            return
        def finish(success):
            assert QThread.currentThread() is origthread
            _sw_.switch_thread(qthread=callbackThread, callback=callback, callbackArg=(success, callbackArg), notifycaller=nop)
            return
        start()
        return

    def download_file(self, url:str, show_prog:bool, callback:Callable, callbackArg:object, callbackThread:QThread) -> None:
        '''
        Download a big file from the given url, and show an ASCII-art progressbar meanwhile.
        The file is downloaded to the temporary folder in the OS. The filepath is passed on
        as argument to the callback.

        :param url:             eg. https://projects.embeetle.com/nucleo/blink_led_STM32F767ZI.zip
        :param show_prog:       Show a progressbar.
        :param callback:        Provide a callback.
        :param callbackArg:     callbackArg=(success, filepath, callbackArg)
        :param callbackThread:  QThread you want the callback to run in.

        '''
        assert threading.current_thread() is not threading.main_thread()
        origthread = QThread.currentThread()
        def start():
            self.__miniEditor.printout("Download: ", "#fce94f")
            self.__miniEditor.printout(url, "#729fcf")
            self.__miniEditor.printout('\n')
            self.start_progbar("Download:") if show_prog else nop()
            QTimer.singleShot(50, download)
            return
        def download(*args):
            j:int    = 0    # Cntr on reporthook calls.
            jmax:int = 1    # Max for cntr, reporthook should update progressbar on overflow.
            def reporthook(*args):
                nonlocal j
                nonlocal jmax
                j += 1
                if j > jmax:
                    j = 0
                    bnr, bsize, tsize = args
                    jmax = int( (tsize/bsize)/100.0 )       # Calculate 'jmax' such that cntr overflow happens 100 times.
                    perc = 100.0 * ((bnr * bsize) / tsize)
                    self.set_progbar_val(perc) if show_prog else nop()
                return
            try:
                """ READ URL """
                filepath, headers = functions.urlretrieve_beetle(url, reporthook=reporthook)
            except urllib.error.ContentTooShortError as e:
                self.close_progbar() if show_prog else nop()
                self.__miniEditor.printout('\n')
                self.__miniEditor.printout("ERROR: Download interrupted\n", "#ef2929")
                self.__miniEditor.printout(f"{e}\n", "#ef2929")
                print("ERROR: Download interrupted\n")
                print(f"{e}\n")
                QTimer.singleShot(100, functools.partial(finish, False, None))
                return
            except urllib.error.HTTPError as e:
                self.close_progbar() if show_prog else nop()
                self.__miniEditor.printout('\n')
                self.__miniEditor.printout("ERROR: HTTP error\n", "#ef2929")
                self.__miniEditor.printout(f"{e}\n", "#ef2929")
                print("ERROR: HTTP error\n")
                print(f"{e}\n")
                QTimer.singleShot(100, functools.partial(finish, False, None))
                return
            except urllib.error.URLError as e:
                self.close_progbar() if show_prog else nop()
                self.__miniEditor.printout('\n')
                self.__miniEditor.printout("ERROR: URL error\n", "#ef2929")
                self.__miniEditor.printout(f"{e}\n", "#ef2929")
                print("ERROR: URL error\n")
                print(f"{e}\n")
                QTimer.singleShot(100, functools.partial(finish, False, None))
                return
            except socket.timeout as e:
                self.close_progbar() if show_prog else nop()
                self.__miniEditor.printout('\n')
                self.__miniEditor.printout("ERROR: Timeout\n", "#ef2929")
                self.__miniEditor.printout(f"{e}\n", "#ef2929")
                print("ERROR: Timeout\n")
                print(f"{e}\n")
                QTimer.singleShot(100, functools.partial(finish, False, None))
                return
            except Exception as e:
                self.close_progbar() if show_prog else nop()
                self.__miniEditor.printout('\n')
                self.__miniEditor.printout("ERROR: URL error\n", "#ef2929")
                self.__miniEditor.printout(f"{e}\n", "#ef2929")
                print("ERROR: URL error\n")
                print(f"{e}\n")
                QTimer.singleShot(100, functools.partial(finish, False, None))
                return

            try:
                """ PRINT HEADERS """
                filepath = filepath.replace('\\', '/')
                filesize = int(os.path.getsize(filepath)/1024)
                headermsg = headers.as_string()
                p = re.compile(r"^(.*?:)", re.MULTILINE)
                headermsg = p.sub("<span style=\"color:#fce94f;\">\\1</span>", headermsg)
                headermsg = headermsg.replace('\n', '<br>')
                self.set_progbar_val(100.0) if show_prog else nop()
                self.close_progbar() if show_prog else nop()
                self.__miniEditor.printout_html('<br>')
                self.__miniEditor.printout_html(f"<span style=\"color:#fce94f;\">File&nbsp;path:</span>&nbsp;{filepath.replace(' ', '&nbsp;')}<br>")
                self.__miniEditor.printout_html(f"<span style=\"color:#fce94f;\">File&nbsp;size:</span>&nbsp;{f'{filesize:,}'.replace(',', ' ')} MB<br>")
                self.__miniEditor.printout_html(headermsg)
                self.__miniEditor.printout_html('<br>')
            except Exception as e:
                try:
                    self.close_progbar() if show_prog else nop()
                except:
                    pass
                self.__miniEditor.printout('\n')
                self.__miniEditor.printout("ERROR: Could not print URL headers.\n", "#ef2929")
                self.__miniEditor.printout(f"{e}\n", "#ef2929")
                QTimer.singleShot(100, functools.partial(finish, False, None))
                return
            QTimer.singleShot(100, functools.partial(finish, True, filepath))
            return
        def finish(success, filepath):
            assert QThread.currentThread() is origthread
            _sw_.switch_thread(qthread=callbackThread, callback=callback, callbackArg=(success, filepath, callbackArg), notifycaller=nop)
            return
        start()
        return

# TODO: --------------------------------------------------------------------------------------------------------------

class MiniEditor(QPlainTextEdit):
    printout_signal        = pyqtSignal(str, str)
    printout_html_signal   = pyqtSignal(str, str)
    clear_signal           = pyqtSignal()
    show_progbar_signal    = pyqtSignal(str)
    set_progbar_val_signal = pyqtSignal(float)
    close_progbar_signal   = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        assert threading.current_thread() is threading.main_thread()
        self.setStyleSheet("""
            QPlainTextEdit {
                color: #ffeeeeec;
                background: #ff000000;
                border-width: 1px;
                border-color: #ff888a85;
                border-style: solid;
                border-radius: 5px;
                padding: 1px;
                margin: 5px 5px 5px 5px;
            }
        """)
        font = QFont()
        font.setFamily("Consolas")
        font.setFixedPitch(False)
        font.setPointSize(12)
        self.setFont(font)
        self.setReadOnly(True)
        self.verticalScrollBar().setStyleSheet(_sb_.get_verticalScrollBar_style())
        self.horizontalScrollBar().setStyleSheet(_sb_.get_horizontalScrollBar_style())
        self.printout_signal.connect(self.printout)
        self.printout_html_signal.connect(self.printout_html)
        self.clear_signal.connect(self.clear)
        self.show_progbar_signal.connect(self.start_progbar)
        self.set_progbar_val_signal.connect(self.set_progbar_val)
        self.close_progbar_signal.connect(self.close_progbar)
        self.__progress_mutex__:threading.Lock = threading.Lock() # Indicates progressbar is 'on' (but could be nonbusy).
        self.__progress_busy__:threading.Lock  = threading.Lock() # Indicates progressbar modification is ongoing.
        self.__progress_perc__:float = 0.0
        self.__tsize:int = 10
        self.__bsize:int = 50
        self.__minipop:MiniPopup = None
        return

    """
    1. PRINT FUNCTION
    """
    @pyqtSlot(str)
    def _printout_(self, outputStr:str):
        self.printout(outputStr)
        return

    @pyqtSlot(str, str)
    def printout(self, outputStr:str, color:str="#ffffff") -> None:
        if not (threading.current_thread() is threading.main_thread()):
            self.printout_signal.emit(outputStr, color)
            return
        if self.__progress_mutex__.locked():
            QTimer.singleShot(40, functools.partial(self.printout, outputStr, color))
            return
        if self.__progress_busy__.locked():
            raise IOError("ERROR: Mini Console progressbar was busy.")
        self.moveCursor(QTextCursor.End)
        self.appendPlainText(outputStr, color)
        return

    @pyqtSlot(str)
    def _printout_html_(self, outputStr):
        self.printout_html(outputStr)
        return

    @pyqtSlot(str, str)
    def printout_html(self, outputStr:str, color:str="#ffffff") -> None:
        if not (threading.current_thread() is threading.main_thread()):
            self.printout_html_signal.emit(outputStr, color)
            return
        if self.__progress_mutex__.locked():
            QTimer.singleShot(40, functools.partial(self.printout_html, outputStr, color))
            return
        if self.__progress_busy__.locked():
            raise IOError("ERROR: Mini Console progressbar was busy.")
        self.moveCursor(QTextCursor.End)
        self.appendHtml(outputStr, color)
        return

    @pyqtSlot()
    def clear(self) -> None:
        if not (threading.current_thread() is threading.main_thread()):
            self.clear_signal.emit()
            return
        if self.__progress_mutex__.locked():
            QTimer.singleShot(40, self.clear)
            return
        if self.__progress_busy__.locked():
            raise IOError("ERROR: Mini Console progressbar was busy.")
        super().clear()
        return

    """
    2. PROGRESS BAR
    """
    @pyqtSlot(str)
    def start_progbar(self, title:str) -> None:
        if not (threading.current_thread() is threading.main_thread()):
            self.show_progbar_signal.emit(title)
            return
        if not self.__progress_mutex__.acquire(blocking=False):
            QTimer.singleShot(10, functools.partial(self.start_progbar, title))
            return
        if not self.__progress_busy__.acquire(blocking=False):
            self.__progress_mutex__.release()
            QTimer.singleShot(10, functools.partial(self.start_progbar, title))
            return
        assert self.__progress_mutex__.locked()
        assert self.__progress_busy__.locked()
        title = title.ljust(self.__tsize).replace(' ', "&nbsp;")
        self.__progress_perc__ = 0.0
        self.appendHtml("&nbsp;"*self.__tsize + "&#95;" * (self.__bsize + 2) + '<br>')
        self.appendHtml(title, color="#fce94f")
        self.appendHtml('|' + "&nbsp;" * self.__bsize + '|' + '<br>')
        self.appendHtml("&nbsp;"*self.__tsize + "&#8254;" * (self.__bsize + 2))
        self.__progress_busy__.release()
        return

    @pyqtSlot(float)
    def set_progbar_val(self, fval:float) -> None:
        fval = min(100.0, fval)
        if not (threading.current_thread() is threading.main_thread()):
            self.set_progbar_val_signal.emit(fval)
            return
        if not self.__progress_mutex__.locked():
            print("WARNING: Attempt to set value on closed progressbar in Mini Console.")
            return
        if not self.__progress_busy__.acquire(blocking=False):
            QTimer.singleShot(10, functools.partial(self.set_progbar_val, fval))
            return
        if self.__progress_perc__ >= fval:
            self.__progress_busy__.release()
            return
        self.__progress_perc__ = fval
        val:int = int( (self.__progress_perc__/100) * self.__bsize )
        cursor:QTextCursor = self.textCursor()
        cursor.beginEditBlock()
        cursor.movePosition(QTextCursor.End,         QTextCursor.MoveAnchor)
        cursor.movePosition(QTextCursor.StartOfLine, QTextCursor.MoveAnchor)
        cursor.movePosition(QTextCursor.Up,          QTextCursor.MoveAnchor)
        cursor.movePosition(QTextCursor.Right,       QTextCursor.MoveAnchor, self.__tsize + 1)
        cursor.movePosition(QTextCursor.EndOfWord,   QTextCursor.KeepAnchor)
        bar = cursor.selectedText()
        if len(bar) > val:
            cursor.setPosition(cursor.position(),    QTextCursor.MoveAnchor)
            cursor.movePosition(QTextCursor.Left,    QTextCursor.KeepAnchor, len(bar) - val)
            cursor.insertHtml("&nbsp;" * (len(bar) - val))
        elif len(bar) < val:
            cursor.setPosition(cursor.position(), QTextCursor.MoveAnchor)
            cursor.movePosition(QTextCursor.Right,   QTextCursor.KeepAnchor, val - len(bar))
            cursor.insertHtml("<span style=\"color:#fce94f;\">&#9632;</span>" * (val - len(bar)))
        cursor.endEditBlock()
        self.__progress_busy__.release()
        return

    @pyqtSlot()
    def close_progbar(self) -> None:
        if not (threading.current_thread() is threading.main_thread()):
            self.close_progbar_signal.emit()
            return
        if not self.__progress_busy__.acquire(blocking=False):
            QTimer.singleShot(10, self.close_progbar)
            return
        self.moveCursor(QTextCursor.End)
        self.__progress_busy__.release()
        try:
            self.__progress_mutex__.release()
        except Exception as e:
            print("WARNING: close_progbar() tried to release self.__progress_mutex__ but it was already released!")
        return

    def is_progbar_open(self) -> bool:
        return self.__progress_mutex__.locked()

    """
    3. INTERNAL FUNCTIONS
    """
    def appendPlainText(self, text:str, color:str="#ffffff") -> None:
        self.moveCursor(QTextCursor.End)
        self.insertPlainText(text, color)
        return

    def appendHtml(self, html:str, color:str="#ffffff") -> None:
        self.moveCursor(QTextCursor.End)
        self.insertHtml(html, color)
        return

    def insertPlainText(self, text:str, color:str="#ffffff") -> None:
        if text == ' ':
            self.insertHtml('&nbsp;')
            return
        # Remove all potential HTML tags.
        text = text.replace('>', '&#62;')
        text = text.replace('<', '&#60;')
        # Replace ' ' with '&nbsp;'
        text = text.replace(' ', '&nbsp;')
        # Replace '\n'
        text = text.replace('\r\n', '\n')
        text = text.replace('\n', '<br>')
        self.insertHtml(text, color)
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
        return

    def insertHtml(self, html:str, color:str="#ffffff") -> None:
        html.replace('\n', '<br>')
        html = f"<span style=\"color:{color};\">" + html + "</span>"
        cursor = self.textCursor()
        cursor.beginEditBlock() # Begin of undo/redo action ('block' is poorly choosen).
        html_blocks = html.split('<br>')
        i = 0
        for block in html_blocks:
            cursor.insertHtml(block)
            i += 1
            if i < len(html_blocks):
                cursor.insertBlock()  # Insert new block/paragraph.
        cursor.endEditBlock()   # End of undo/redo action.
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
        return

    # TODO: --------------------------------------------------------------------------------------------------------------
    """
    4. CONTEXT MENU
    """
    def contextMenuEvent(self, event:QContextMenuEvent) -> None:
        if self.__minipop is None:
            self.__minipop = MiniPopup(miniEditor=self)
        point = event.globalPos()
        self.__minipop.exec_(point)
        return


def get_consolepopup_stylesheet(font_scale, icon_scale):
    '''
    Stylesheet for the rightmouse button menu. Note: the size of the icons are unfortunately not decided here.
    After applying this stylesheet to a popupMenu, you've got to write the following codeline:

        components.TheSquid.customize_menu_style(self, enlarge=...)

    with the parameter 'enlarge' being the enlargement of the icons you want, compared to the standard icon sizes
    of other menus (like the toplevel menus).

    '''
    styleStr = f"""
        QMenu {{
            font-family: Inconsolata;
            font-size: {font_scale}pt;
            color: #ffeeeeec;
            background-color: qlineargradient(x1:0, y1:1, x2:1, y2:1,
                                              stop: 0 #ff2e3436, stop: 1 #ff888a85);
            border-color: #ffd3d7cf;
            border-style: solid;
            border-width: 1px;
            border-radius: 2px;
            margin: 0px 0px 0px 0px;
        }}
        QMenu::item {{
            border: none;
            padding: 2px {int(1.1*icon_scale)}px 2px {int(1.1*icon_scale)}px;
            spacing: {int(0.30*icon_scale)}px;
        }}
        QMenu::item:selected {{
            font-size: {font_scale+1}pt;
            color: #ffffffff;
            background-color: #883465a4;
            border-color: 1px solid #cc204a87;
        }}
        QMenu::separator {{
            height: 2px;
            margin: 2px {int(0.20*icon_scale)}px 2px {int(0.20*icon_scale)}px;
        }}
    """
    return styleStr

class MiniPopup(QMenu):
    def __init__(self, miniEditor:MiniEditor) -> None:
        super().__init__()
        self.__miniEditor = weakref.ref(miniEditor)
        menuCopy          = QAction(functions.create_icon("icons/edit/edit-copy.png")      , "Copy         Ctrl+C  ", self)
        menuCopyAll       = QAction(functions.create_icon("icons/edit/edit-copy-all.png")  , "Copy All     Ctrl+A+C", self)
        self.addAction(menuCopy)
        self.addAction(menuCopyAll)
        menuCopy.triggered.connect(self.__copy)
        menuCopyAll.triggered.connect(self.__copyAll)
        try:
            # Embeetle
            self.setStyleSheet(get_consolepopup_stylesheet(font_scale=data.get_console_font_pointsize(),
                                                           icon_scale=data.get_console_button_pixelsize()))
            components.thesquid.TheSquid.customize_menu_style(self, enlarge=data.get_console_button_pixelsize() - data.get_custom_menu_pixelsize())
        except Exception as e:
            # Beetle Updater
            self.setStyleSheet(get_consolepopup_stylesheet(font_scale=data.get_console_font_pointsize(),
                                                           icon_scale=50))
            functions.customize_menu_style(self, enlarge=50 - data.get_custom_menu_pixelsize())
        return

    def __copy(self):
        miniEditor = self.__miniEditor()
        miniEditor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_C, Qt.ControlModifier, ''))
        return

    def __copyAll(self):
        miniEditor = self.__miniEditor()
        miniEditor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.ControlModifier, ''))
        miniEditor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_C, Qt.ControlModifier, ''))
        QTimer.singleShot(100, lambda: miniEditor.moveCursor(QTextCursor.End))
        QTimer.singleShot(200, lambda: miniEditor.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_A, Qt.ControlModifier, '')))
        QTimer.singleShot(300, lambda: miniEditor.moveCursor(QTextCursor.End))
        return
