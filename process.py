from __future__ import annotations
from typing import *
from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *
import os, time, re, data, threading, enum, sys
nop = lambda *a, **k: None
EOL = '\r\n' if os.name == "nt" else '\n'

class trialContextManager:
    def __enter__(self): pass
    def __exit__(self, *args): return True
trial = trialContextManager()

class ProcessErr(enum.Enum):
    NORMAL_EXIT     = 0
    PROC_MUTEX      = 1
    SUBPROC_MUTEX   = 2
    FAILED_TO_START = 3
    CRASH_EXIT      = 4
    KILLED          = 5

def get_prompts() -> List[str]:
    return ["(gdb)", ">>>", "..."]

class Process(QProcess):
    output_sig      = pyqtSignal(str)   # Tied to body.__printout__().
    output_html_sig = pyqtSignal(str)   # Tied to body.__printout_html__().

    def __init__(self) -> None:
        '''
        Create a Process()-object - subclassed from QProcess - to execute
        commands.

        '''
        # 1. Setup
        super().__init__()
        self.setProcessChannelMode(QProcess.MergedChannels)
        # 2. Variable initializations
        self.processMutex    = threading.Lock()
        self.subprocessMutex = threading.Lock()
        self.__next_subprocess_start_ifunc = None  # Inner function: next_subprocess_start()
        self.__catch_finish_ifunc          = None  # Inner function: catch_finish()
        self.__killed = False
        # 3. Process environment (NEW!)
        env = QProcessEnvironment.systemEnvironment()
        self.setProcessEnvironment(env)
        self.__old_PATH = os.environ["PATH"]
        self.__new_PATH = os.environ["PATH"]
        return

    def execute_subcommand(self, subcommand:str) -> None:
        assert self.__next_subprocess_start_ifunc is not None
        assert self.__next_subprocess_start_ifunc.__name__ == "next_subprocess_start"
        assert self.processMutex.locked()
        assert not self.subprocessMutex.locked()
        assert self.state() == QProcess.Running
        self.__next_subprocess_start_ifunc(subcommand)
        return

    def execute_command(self, command:str, subproc_callback:Callable, process_callback:Callable) -> None:
        '''
        :param command:             Command string to get executed.
        :param subproc_callback:    Callback when subprocess has finished. @param: ()
        :param proc_callback:       Callback when process has finished.    @param: (success, code) # exitCode or errCode

        Note: there are two ways to enter a subcommand:
            > For automatic mode:
              Provide a subproc_callback(). It gets called as soon as the prompt is detected in the catched
              output. The inner function next_subprocess_start() gets stored in the variable
              self.__next_subprocess_start_func so you can call it with the next subcommand as parameter.
            > For manual mode:
              Don't provide a subproc_callback(). The inner function next_subprocess_start() gets stored in
              the variable self.__next_subprocess_start_func as soon as the prompt is detected in the catched
              output. Wait until self.is_subprocess_busy() returns False to be sure you can call
              self.execute_subcommand().

        '''
        command = command.strip()
        prompt_candidate = ''
        def process_start():
            self.output_sig.emit('\n')
            self.__killed = False
            if not self.processMutex.acquire(blocking=False):
                process_abort(ProcessErr.PROC_MUTEX)
                return
            if not self.subprocessMutex.acquire(blocking=False):
                process_abort(ProcessErr.SUBPROC_MUTEX)
                return
            assert self.__catch_finish_ifunc is None
            assert self.__next_subprocess_start_ifunc is None
            assert self.receivers(self.readyRead)     == 0
            assert self.receivers(self.errorOccurred) == 0
            assert self.receivers(self.finished)      == 0
            self.readyRead.connect(catch_output)
            self.errorOccurred.connect(catch_error)
            self.finished.connect(catch_finish)
            self.__catch_finish_ifunc = catch_finish
            def cmd_gen(command):
                self.__old_PATH = os.environ["PATH"]
                os.environ["PATH"] = self.__new_PATH
                self.start(command)
                started = self.waitForStarted(50)
                os.environ["PATH"] = self.__old_PATH
                if not started:
                    process_abort(ProcessErr.FAILED_TO_START)
                return
            def cmd_py(command):
                command = "python -i" + '\r\n'
                cmd_gen(command)
                return
            def cmd_cd(command):
                path = command.replace('cd', '', 1).strip()   # Remove 'cd'
                path = path.replace('"', '').strip()          # Remove the " characters
                path = path.replace('\\', '/')
                path = path[0:-1] if path.endswith('/') else path
                cwd = os.getcwd().replace('\\', '/')
                cwd = cwd[0:-1] if cwd.endswith('/') else cwd
                try:
                    path = str(os.path.expanduser(path))
                except:
                    self.output_html_sig.emit(f"""ERROR: the given path has wrong format:<br>&nbsp;&nbsp;&nbsp;&nbsp;<span$style=\"color:#ce5c00;\">{path}</span><br>""".replace(' ', '&nbsp;').replace('$',' '))
                    catch_finish(0, QProcess.CrashExit)  # Manual exit!
                    return
                if not os.path.isabs(path):
                    path = cwd + '/' + path
                    path = path.replace('//', '/')
                if not os.path.isdir(path):
                    if (path.split('/')[-1] == path.split('/')[-2]):
                        parent = os.path.dirname(path).replace('\\', '/')
                        parent = parent[0:-1] if parent.endswith('/') else parent
                        if parent == cwd:
                            self.output_html_sig.emit(f"""NOTE: you are already in:<br>&nbsp;&nbsp;&nbsp;&nbsp;<span$style=\"color:#c4a000;\">{cwd}</span><br>""".replace(' ', '&nbsp;').replace('$',' '))
                            catch_finish(0, QProcess.NormalExit)  # Manual exit!
                            return
                    self.output_html_sig.emit(f"""ERROR: the given path does not exist:<br>&nbsp;&nbsp;&nbsp;&nbsp;<span$style=\"color:#ce5c00;\">{path}</span><br>""".replace(' ', '&nbsp;').replace('$',' '))
                    catch_finish(0, QProcess.CrashExit)  # Manual exit!
                    return
                assert os.path.isdir(path)
                os.chdir(path)
                self.output_sig.emit('\n')
                catch_finish(0, QProcess.NormalExit)  # Manual exit!
                return
            def cmd_dir(command):
                itemList = os.listdir(os.getcwd())
                self.output_sig.emit('\n')
                for item in itemList:
                    # > Find item info
                    itempath = os.path.join(os.getcwd(), item).replace("\\", "/")
                    itemtime = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(itempath)))
                    itemtype = ""
                    if os.path.isfile(itempath):
                        itemtype = "<FILE>"
                    else:
                        itemtype = "<DIR>"
                    # > Align Strings
                    itemtime = itemtime.ljust(22)
                    itemtype = itemtype.ljust(8)
                    self.output_sig.emit(itemtime + "   " + itemtype + "   " + item + "\n")
                self.output_sig.emit('\n')
                # Manual exit!
                catch_finish(0, QProcess.NormalExit)
                return
            def cmd_path(command):
                # WINDOWS
                if sys.platform.lower().startswith('win'):
                    try:
                        p = re.compile(r"([Pp][Aa][Tt][Hh]\s*=)([^;]+);(\s*%[Pp][Aa][Tt][Hh]%)", re.MULTILINE)
                        match = p.search(command)
                        newpath = match.group(2).strip().replace('/', EOL)
                        var = match.group(1).replace('=', '').strip()
                        self.__add_to_PATH_begin__(var=var, newpath=newpath)
                        catch_finish(0, QProcess.NormalExit)
                        return
                    except:
                        try:
                            p = re.compile(r"([Pp][Aa][Tt][Hh]\s*=)(\s*%[Pp][Aa][Tt][Hh]%);([^;]+)", re.MULTILINE)
                            match = p.search(command)
                            newpath = match.group(3).strip().replace('/', EOL)
                            var = match.group(1).replace('=', '').strip()
                            self.__add_to_PATH_end__(var=var, newpath=newpath)
                            catch_finish(0, QProcess.NormalExit)
                            return
                        except:
                            if command.upper() == "PATH":
                                p = re.compile(r"([Pp][Aa][Tt][Hh])", re.MULTILINE)
                                match = p.search(command)
                                var = match.group(1)
                                self.__print_PATH__(var=var)
                                catch_finish(0, QProcess.NormalExit)
                                return
                            else:
                                self.__old_PATH = os.environ["PATH"]
                                os.environ["PATH"] = self.__new_PATH
                                self.start(command)
                                success = self.waitForStarted(-1)
                                os.environ["PATH"] = self.__old_PATH

                                if not success:
                                    self.output_sig.emit(f'\n')
                                    self.output_sig.emit(f"Could not interpret your command \"{command}\"\n")
                                    self.output_sig.emit(f"If you want to add something to your PATH environment variable,\n")
                                    self.output_sig.emit(f"please issue the command:\n")
                                    self.output_sig.emit(f"    PATH=C:\\path\\to\\folder;%PATH%\n")
                                    self.output_sig.emit(f"or:\n")
                                    self.output_sig.emit(f"    PATH=%PATH%;C:\\path\\to\\folder\n")
                                    self.output_sig.emit(f'\n')
                                    catch_finish(0, QProcess.NormalExit)
                                return
                # LINUX
                try:
                    p = re.compile(r"([Pp][Aa][Tt][Hh]\s*=)([^:]+):(\s*\$[Pp][Aa][Tt][Hh])", re.MULTILINE)
                    match = p.search(command)
                    newpath = match.group(2).strip().replace('/', EOL)
                    var = match.group(1).replace('=', '').strip()
                    self.__add_to_PATH_begin__(var=var, newpath=newpath)
                    catch_finish(0, QProcess.NormalExit)
                    return
                except:
                    try:
                        p = re.compile(r"([Pp][Aa][Tt][Hh]\s*=)(\s*\$[Pp][Aa][Tt][Hh]):([^:]+)", re.MULTILINE)
                        match = p.search(command)
                        newpath = match.group(3).strip().replace('/', EOL)
                        var = match.group(1).replace('=', '').strip()
                        self.__add_to_PATH_end__(var=var, newpath=newpath)
                        catch_finish(0, QProcess.NormalExit)
                        return
                    except:
                        if command.upper() == "PATH":
                            p = re.compile(r"([Pp][Aa][Tt][Hh])", re.MULTILINE)
                            match = p.search(command)
                            var = match.group(1)
                            self.__print_PATH__(var=var)
                            catch_finish(0, QProcess.NormalExit)
                            return
                        else:
                            self.__old_PATH = os.environ["PATH"]
                            os.environ["PATH"] = self.__new_PATH
                            self.start(command)
                            success = self.waitForStarted(-1)
                            os.environ["PATH"] = self.__old_PATH

                            if not success:
                                self.output_sig.emit(f'\n')
                                self.output_sig.emit(f'\n')
                                self.output_sig.emit(f"Could not interpret your command \"{command}\"\n")
                                self.output_sig.emit(f"If you want to add something to your PATH environment variable,\n")
                                self.output_sig.emit(f"please issue the command:\n")
                                self.output_sig.emit(f"    export PATH=path/to/folder:$PATH\n")
                                self.output_sig.emit(f"or:\n")
                                self.output_sig.emit(f"    export PATH=$PATH:path/to/folder\n")
                                self.output_sig.emit(f'\n')
                                catch_finish(0, QProcess.NormalExit)
                            return
                return
            nonlocal command
            if command.startswith(("cd ", "cd.")):
                cmd_cd(command)
            elif command == "dir":
                cmd_dir(command)
            elif command.strip().encode('utf-8') == b'python':
                cmd_py(command)
            elif command.upper().startswith(("PATH", "SET PATH", "EXPORT PATH")):
                cmd_path(command)
            else:
                cmd_gen(command)
            return
        'NATIVE SIGNAL CATCHER'
        def catch_output():
            nonlocal prompt_candidate
            _data_ = bytes(self.readAll()).decode().replace('\r\n', '\n')
            eolIndex = _data_.rfind('\n')
            prompt_candidate = _data_[eolIndex + 1:] if eolIndex >= 0 else (prompt_candidate + _data_)
            prompt_candidate = prompt_candidate.strip()
            # Forward data.
            self.output_sig.emit(_data_)
            # Compare to prompts.
            if prompt_candidate in get_prompts():
                prompt_candidate = ''
                assert self.__next_subprocess_start_ifunc is None
                self.__next_subprocess_start_ifunc = next_subprocess_start
                self.subprocessMutex.release()
                subproc_callback() if subproc_callback is not None else nop()
            return
        'NATIVE SIGNAL CATCHER'
        def catch_error(error:QProcess.ProcessError):
            return
        'NATIVE SIGNAL CATCHER'
        def catch_finish(exitCode:int, exitStatus:QProcess.ExitStatus):
            self.__catch_finish_ifunc = None
            if self.__killed:
                self.__killed = False
                process_abort(ProcessErr.KILLED)
                return
            if exitStatus == QProcess.NormalExit:
                process_finish(exitCode)
                return
            if exitStatus == QProcess.CrashExit:
                process_abort(ProcessErr.CRASH_EXIT)
                return
            assert False
        def next_subprocess_start(subcommand):
            self.__next_subprocess_start_ifunc = None
            self.output_sig.emit('\n')
            if self.__killed:
                self.__killed = False
                process_abort(ProcessErr.KILLED)
                return
            if not self.subprocessMutex.acquire(blocking=False):
                process_abort(ProcessErr.SUBPROC_MUTEX)
                return
            self.write(subcommand)
            return
        def process_abort(errCode:ProcessErr):
            self.__killed = False
            self.__next_subprocess_start_ifunc = None
            self.__catch_finish_ifunc = None
            with trial: self.readyRead.disconnect(catch_output)
            with trial: self.errorOccurred.disconnect(catch_error)
            with trial: self.finished.disconnect(catch_finish)
            self.processMutex.release()    if self.processMutex.locked()    else nop()
            self.subprocessMutex.release() if self.subprocessMutex.locked() else nop()
            process_callback(False, errCode) if process_callback is not None else nop()
            return
        def process_finish(exitCode:int):
            self.__killed = False
            self.__next_subprocess_start_ifunc = None
            self.__catch_finish_ifunc = None
            with trial: self.readyRead.disconnect(catch_output)
            with trial: self.errorOccurred.disconnect(catch_error)
            with trial: self.finished.disconnect(catch_finish)
            self.processMutex.release()    if self.processMutex.locked()    else nop()
            self.subprocessMutex.release() if self.subprocessMutex.locked() else nop()
            process_callback(True, exitCode) if process_callback is not None else nop()
            return
        process_start()
        return

    """
    1. QPROCESS OVERRIDES
    """
    def start(self, command:str) -> None:
        '''
        Start the process with given command.

        '''
        super().start(command.strip())
        return

    def write(self, subcommand:str) -> None:
        '''
        Write a string (subcommand) to the process.

        '''
        subcommand = subcommand.replace('\r\n', '\n')
        super().write(subcommand.replace('\n', EOL).encode('utf-8'))
        return

    """
    3. GETTERS
    """
    def is_process_busy(self) -> bool:
        if (self.state() == QProcess.NotRunning) and (self.processMutex.locked() == False):
            return False
        if self.state() == QProcess.Starting:
            assert self.processMutex.locked()
            return True
        if self.state() == QProcess.Running:
            assert self.processMutex.locked()
            return True
        assert not self.processMutex.locked()
        return False

    def is_subprocess_busy(self) -> bool:
        if self.subprocessMutex.locked():
            assert self.processMutex.locked()
            assert self.state() == QProcess.Running
            return True
        return False

    """
    4. KILL PROCESS
    """
    def kill_current_process(self) -> None:
        if self.state() == QProcess.NotRunning:
            return
        self.__killed = True
        self.kill()
        self.output_sig.emit('')
        self.output_sig.emit('    > > > PROCESS KILLED')
        self.output_sig.emit('')
        # Happens automatically:
        # catch_finish(1, QProcess.CrashExit)
        return

    """
    5. ENVIRONMENT VARIABLE 'PATH'
    """
    def __print_PATH__(self, var:str) -> None:
        '''
        Print 'PATH' environment variable.
        :param var:     Usually "PATH" or "path".

        '''
        envObj = self.processEnvironment()
        curpath = envObj.value(var)
        curpathList = curpath.split(";")
        for p in curpathList:
            self.output_sig.emit(" > " + p + "\n")
        return

    def __add_to_PATH_end__(self, var:str, newpath:str) -> None:
        '''
        Add given 'newpath' to the 'PATH' environment variable.
        :param var:         Usually "PATH" or "path".
        :param newpath:     Absolute path.

        '''
        # 1. Insert the path into QProcess()-instance for its children
        envObj = self.processEnvironment()
        envObj.insert(var, envObj.value(var) + ";" + newpath)
        self.setProcessEnvironment(envObj)
        # 2. Insert the path into self.__new_PATH for oneself
        self.__new_PATH = self.__new_PATH + ';' + newpath
        return

    def __add_to_PATH_begin__(self, var:str, newpath:str) -> None:
        '''
        Add given 'newpath' to the 'PATH' environment variable.
        :param var:         Usually "PATH" or "path".
        :param newpath:     Absolute path.

        '''
        # 1. Insert the path into QProcess()-instance for its children
        envObj = self.processEnvironment()
        envObj.insert(var, newpath + ';' + envObj.value(var))
        self.setProcessEnvironment(envObj)
        # 2. Insert the path into self.__new_PATH for oneself
        self.__new_PATH = newpath + ';' + self.__new_PATH
        return

    def add_process_environ_var(self, var:str, value:str) -> None:
        '''

        '''
        envObj = self.processEnvironment()
        envObj.insert(var, value)
        self.setProcessEnvironment(envObj)
        return



# About self.__prompt_candidate
# ------------------------------
# Bug discovered in checking the self.__prompt_candidate
# variable. Sometimes a prompt is not preceded
# by a newline character.
# For example:
#
# C:\..\myProject>python -i
# >>> a = 5>>>
#
# In the example above, the user hits the Enter
# key after typing "a = 5". The Enter key causes
# the subcommand "a = 5" to execute. But there is
# no output from that. So the process shows a new
# prompt ">>>" without actually outputting a newline
# character.
#
# Note: My console prints the newline character
# artificially for obvious aesthetic reasons.
#
# Solution
# --------
# I believe the bug is solved by resetting the
# self.__prompt_candidate variable on several locations.
#
