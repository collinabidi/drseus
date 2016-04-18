from bdb import BdbQuit
from cmd import Cmd
from multiprocessing import Value
from os import makedirs
from os.path import exists
from pdb import set_trace
from readline import read_history_file, set_history_length, write_history_file
from select import select
from subprocess import CalledProcessError, check_output
from sys import stdin
from threading import Thread
from traceback import print_exc

from .arguments import inject
from .fault_injector import fault_injector
from .jtag import jtag
from .power_switch import power_switch
from .simics import simics


# TODO: add background read thread and interact command
#       (remove dut read and dut command)
class supervisor(Cmd):
    def __init__(self, campaign, options):
        options.injections = 0
        options.latent_iterations = 0
        options.compare_all = False
        options.extract_blocks = False
        if options.power_switch_outlet is not None:
            switch = power_switch(options)
        else:
            switch = None
        self.drseus = fault_injector(campaign, options, switch)
        if campaign['simics']:
            self.drseus.debugger.launch_simics(
                'gold-checkpoints/'+str(self.drseus.db.campaign['id'])+'/' +
                str(self.drseus.db.campaign['checkpoints'])+'_merged')
            self.drseus.debugger.continue_dut()
        else:
            self.drseus.debugger.reset_dut()
        self.prompt = 'DrSEUs> '
        Cmd.__init__(self)
        if exists('supervisor_history'):
            read_history_file('supervisor_history')
        set_history_length(options.history_length)
        if campaign['aux']:
            self.__class__ = aux_supervisor

    def preloop(self):
        print('Welcome to DrSEUs!\n')
        self.do_info()
        self.do_help(None)

    def precmd(self, line):
        write_history_file('supervisor_history')
        return line

    def complete(self, text, state):
        ret = Cmd.complete(self, text, state)
        if ret:
            return ret+' '
        else:
            return ret

    def do_info(self, arg=None):
        """Print information about the current campaign"""
        print(str(self.drseus))

    def do_update_dut_timeout(self, arg, aux=False):
        """Update DUT serial timeout (in seconds)"""
        try:
            new_timeout = int(arg)
        except ValueError:
            print('Invalid value entered')
            return
        if self.drseus.db.campaign['simics']:
            self.drseus.debugger.timeout = new_timeout
        if aux:
            self.drseus.debugger.aux.default_timeout = new_timeout
            self.drseus.debugger.aux.serial.timeout = new_timeout
        else:
            self.drseus.debugger.dut.default_timeout = new_timeout
            self.drseus.debugger.dut.serial.timeout = new_timeout

    def do_command_dut(self, arg, aux=False):
        """Send DUT device a command and interact, interrupt with ctrl-c"""
        read_thread = Thread(target=(self.drseus.debugger.aux.command if aux
                                     else self.drseus.debugger.dut.command),
                             args=[arg])
        read_thread.start()
        try:
            while read_thread.is_alive():
                if select([stdin], [], [], 0.1)[0]:
                    if aux:
                        self.drseus.debugger.aux.write(stdin.readline()+'\n')
                    else:
                        self.drseus.debugger.dut.write(stdin.readline()+'\n')
        except KeyboardInterrupt:
            if self.drseus.db.campaign['simics']:
                self.drseus.debugger.continue_dut()
            if aux:
                self.drseus.debugger.aux.write('\x03')
            else:
                self.drseus.debugger.dut.write('\x03')
            read_thread.join()

    def do_read_dut(self, arg=None, aux=False):
        """Read from DUT, interrupt with ctrl-c"""
        try:
            if aux:
                self.drseus.debugger.aux.read_until(continuous=True)
            else:
                self.drseus.debugger.dut.read_until(continuous=True)
        except KeyboardInterrupt:
            if self.drseus.db.campaign['simics']:
                self.drseus.debugger.continue_dut()

    def do_send_file_dut(self, arg, aux=False):
        """Send file to DUT, defaults to sending campaign files"""
        if aux:
            self.drseus.debugger.aux.send_files(arg, attempts=1)
        else:
            self.drseus.debugger.dut.send_files(arg, attempts=1)

    def do_get_file_dut(self, arg, aux=False):
        """Retrieve file from DUT device"""
        output = ('campaign-data/'+str(self.drseus.db.campaign['id']) +
                  '/results/'+str(self.drseus.result['id'])+'/')
        makedirs(output)
        output += '/'+arg
        if aux:
            self.drseus.debugger.aux.get_file(arg, output, attempts=1)
        else:
            self.drseus.debugger.dut.get_file(arg, output, attempts=1)
        print('File saved to '+output)

    def do_supervise(self, arg):
        """Supervise for targeted runtime (in seconds) or iterations"""
        if 's' in arg:
            try:
                timer = int(arg.replace('s', ''))
            except ValueError:
                print('Invalid value entered')
                return
            iteration_counter = None
        else:
            try:
                supervise_iterations = int(arg)
            except ValueError:
                print('Invalid value entered')
                return
            iteration_counter = Value('L', supervise_iterations)
            timer = None
        if self.drseus.db.campaign['simics']:
            self.drseus.debugger.close()
        else:
            self.drseus.debugger.dut.flush()
        self.drseus.db.result.update({'outcome_category': 'DrSEUs',
                                      'outcome': 'Pre-supervise'})
        with self.drseus.db as db:
            db.log_result()
        try:
            self.drseus.inject_campaign(iteration_counter, timer)
        except KeyboardInterrupt:
            with self.drseus.db as db:
                db.log_event('Information', 'User', 'Interrupted',
                             db.log_exception)
            self.drseus.db.result.update({'outcome_category': 'Incomplete',
                                          'outcome': 'Interrupted'})
            with self.drseus.db as db:
                db.log_result()
        except:
            print_exc()
            with self.drseus.db as db:
                db.log_event('Error', 'DrSEUs', 'Exception', db.log_exception)
            self.drseus.db.result.update({'outcome_category': 'Incomplete',
                                          'outcome': 'Uncaught exception'})
            with self.drseus.db as db:
                db.log_result()
        if self.drseus.db.campaign['simics']:
            self.drseus.debugger.launch_simics(
                'gold-checkpoints/'+str(self.drseus.db.campaign['id'])+'/' +
                str(self.drseus.db.campaign['checkpoints'])+'_merged')
            self.drseus.debugger.continue_dut()

    def do_inject(self, arg):
        if not isinstance(self.drseus.debugger, jtag) and \
                not isinstance(self.drseus.debugger, simics):
            print('injections not supported without debugger')
            return
        if '-h' in arg.split() or '--help' in arg.split():
            return self.help_inject()
        try:
            options = inject.parse_args(arg.split())
        except:
            return
        self.drseus.options.iterations = options.iterations
        self.drseus.options.injections = options.injections
        self.drseus.options.selected_targets = options.selected_targets
        self.drseus.options.selected_target_indices = \
            options.selected_target_indices
        self.drseus.options.selected_registers = options.selected_registers
        self.drseus.options.latent_iterations = options.latent_iterations
        self.drseus.options.processes = options.processes
        self.drseus.options.compare_all = options.compare_all
        self.drseus.options.extract_blocks = options.extract_blocks
        if options.iterations is None:
            iteration_counter = None
        else:
            iteration_counter = Value('L', options.iterations)
        if self.drseus.db.campaign['simics']:
            self.drseus.debugger.close()
        else:
            self.drseus.debugger.dut.flush()
        self.drseus.db.result.update({'outcome_category': 'DrSEUs',
                                      'outcome': 'Pre-inject'})
        with self.drseus.db as db:
            db.log_result()
        try:
            self.drseus.inject_campaign(iteration_counter)
        except KeyboardInterrupt:
            with self.drseus.db as db:
                db.log_event('Information', 'User', 'Interrupted',
                             db.log_exception)
            self.drseus.debugger.close()
            self.drseus.db.result.update({'outcome_category': 'Incomplete',
                                          'outcome': 'Interrupted'})
            with self.drseus.db as db:
                db.log_result()
        except:
            print_exc()
            with self.drseus.db as db:
                db.log_event('Error', 'DrSEUs', 'Exception',
                             db.log_exception)
            self.drseus.debugger.close()
            self.drseus.db.result.update({'outcome_category': 'Incomplete',
                                          'outcome': 'Uncaught exception'})
            with self.drseus.db as db:
                db.log_result()
        if self.drseus.db.campaign['simics']:
            self.drseus.debugger.launch_simics(
                'gold-checkpoints/'+str(self.drseus.db.campaign['id'])+'/' +
                str(self.drseus.db.campaign['checkpoints'])+'_merged')
            self.drseus.debugger.continue_dut()

    def help_inject(self):
        inject.prog = 'inject'
        inject.print_help()

    def do_log(self, arg):
        """Log current status as a result"""
        self.drseus.db.result.update({
            'outcome_category': 'DrSEUs',
            'outcome': arg if arg else 'Manual entry'})
        with self.drseus.db as db:
            db.log_result()

    def do_event(self, arg):
        """Log an event"""
        if not arg:
            arg = input('Event type: ')
        description = input('Event description: ')
        with self.drseus.db as db:
            db.log_event('Information', 'User', arg, description)

    def do_power_cycle(self, arg=None):
        """Power cycle device using web power switch"""
        if hasattr(self.drseus.debugger, 'power_switch') and \
            self.drseus.debugger.power_switch is not None and \
                hasattr(self.drseus.debugger, 'power_cycle_dut'):
            self.drseus.debugger.power_cycle_dut()
        else:
            print('Web power switch not configured, unable to power cycle')

    def do_debug(self, arg=None):
        """Start PDB"""
        try:
            set_trace()
        except BdbQuit:
            pass

    def do_shell(self, arg):
        """Pass command to a system shell when line begins with \"!\""""
        with self.drseus.db as db:
            event = db.log_event('Information', 'Shell', arg, success=False)
        try:
            output = check_output(arg, shell=True, universal_newlines=True)
            print(output, end='')
            event['description'] = output
            with self.drseus.db as db:
                db.log_event_success(event)
        except CalledProcessError as error:
            print(error.output, end='')
            event['description'] = error.output
            with self.drseus.db as db:
                db.update('event', event)

    def do_exit(self, arg=None):
        """Exit DrSEUs"""
        self.drseus.close()
        return True

    do_EOF = do_exit


class aux_supervisor(supervisor):
    def do_update_aux_timeout(self, arg):
        """Update AUX serial timeout (in seconds)"""
        self.do_update_dut_timeout(arg, aux=True)

    def do_command_aux(self, arg):
        """Send AUX device a command and interact, interrupt with ctrl-c"""
        self.do_dut_command(arg, aux=True)

    def do_read_aux(self, arg):
        """Read from AUX, interrupt with ctrl-c"""
        self.do_read_dut(arg, aux=True)

    def do_send_file_aux(self, arg):
        """Send (comma-seperated) files to AUX, defaults to campaign files"""
        self.do_send_dut_files(arg, aux=True)

    def do_get_file_aux(self, arg):
        """Retrieve file from AUX device"""
        self.do_get_dut_file(arg, aux=True)