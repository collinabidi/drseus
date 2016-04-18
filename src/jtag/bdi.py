from time import sleep

from ..error import DrSEUsError
from ..targets import get_targets
from . import jtag


class bdi(jtag):
    error_messages = ['syntax error in command',
                      'timeout while waiting for halt',
                      'wrong state for requested command', 'read access failed']

    def __init__(self, database, options):
        self.prompts = ['P2020>']
        if hasattr(options, 'selected_targets'):
            selected_targets = options.selected_targets
        else:
            selected_targets = None
        if hasattr(options, 'selected_registers'):
            selected_registers = options.selected_registers
        else:
            selected_registers = None
        self.targets = get_targets('p2020', 'jtag', selected_targets,
                                   selected_registers)
        self.port = 23
        super().__init__(database, options)
        self.open()

    def __str__(self):
        string = ('BDI3000 at '+self.options.debugger_ip_address +
                  ' port '+str(self.port))
        return string

    def close(self):
        self.telnet.write(bytes('quit\r', encoding='utf-8'))
        super().close()

    def reset_bdi(self):
        with self.db as db:
            event = db.log_event('Warning', 'Debugger', 'Reset BDI',
                                 success=False)
        self.telnet.write(bytes('boot\r\n', encoding='utf-8'))
        self.telnet.close()
        if self.db.result:
            self.db.result['debugger_output'] += 'boot\n'
        else:
            self.db.campaign['debugger_output'] += 'boot\n'
        sleep(1)
        self.connect_telnet()
        sleep(1)
        self.command(None, error_message='', log_event=False)
        with self.db as db:
            db.log_event_success(event)

    def reset_dut(self, attempts=5):
        expected_output = [
            '- TARGET: processing user reset request',
            '- BDI asserts HRESET',
            '- Reset JTAG controller passed',
            '- JTAG exists check passed',
            '- BDI removes HRESET',
            '- TARGET: resetting target passed',
            '- TARGET: processing target startup \.\.\.\.',
            '- TARGET: processing target startup passed']
        try:
            super().reset_dut(expected_output, 1)
        except DrSEUsError:
            self.reset_bdi()
            super().reset_dut(expected_output, max(attempts-1, 1))

    def halt_dut(self):
        super().halt_dut('halt 0 1', [
            '- TARGET: core #0 has entered debug mode',
            '- TARGET: core #1 has entered debug mode'])

    def continue_dut(self):
        super().continue_dut('go 0 1')

    def select_core(self, core):
        self.command('select '+str(core), ['Target CPU', 'Core state'],
                     'Error selecting core')

    def get_mode(self):
        msr = int(self.get_register_value('msr'), base=16)
        supervisor = not bool(msr & (1 << 14))
        return 'supervisor' if supervisor else 'user'

    def set_mode(self, mode='supervisor'):
        msr = list(bin(int(self.get_register_value('msr'), base=16)))
        if mode == 'supervisor':
            msr[-15] = '0'
        else:
            msr[-15] = '1'
        msr = hex(int(''.join(msr), base=2))
        self.set_register_value('msr', msr)
        with self.db as db:
            db.log_event('Information', 'Debugger', 'Set processor mode',
                         mode, success=True)

    def command(self, command, expected_output=[], error_message=None,
                log_event=True):
        return super().command(command, expected_output, error_message,
                               log_event, '\r\n', False)

    def get_register_value(self, register_info):
        if register_info == 'msr':
            return self.command(
                'rd msr', [':'], 'Error getting register value'
            ).split('\r')[0].split(':')[1].split()[0]
        target = self.targets[register_info['target']]
        if 'target_index' in register_info:
            target_index = register_info['target_index']
        else:
            target_index = 0
        if 'register_alias' in register_info:
            register_name = register_info['register_alias']
        else:
            register_name = register_info['register']
        register = target['registers'][register_info['register']]
        if 'type' in target and target['type'] == 'memory_mapped':
            command = 'md'
            if 'bits' in register:
                bits = register['bits']
                if bits == 8:
                    command += 'b'
                elif bits == 16:
                    command += 'h'
                elif bits == 64:
                    command += 'd'
            address = target['base'][target_index] + register['offset']
            buff = self.command(command+' '+hex(address)+' 1', [':'],
                                'Error getting register value')
        elif 'SPR' in register:
            buff = self.command('rdspr ' + str(register['SPR']), [':'],
                                'Error getting register value')
        elif 'PMR' in register:
            buff = self.command('rdpmr ' + str(register['PMR']), [':'],
                                'Error getting register value')
        else:
            buff = self.command('rd '+register_name, [':'],
                                'Error getting register value')
        return buff.split('\r')[0].split(':')[1].split()[0]

    def set_register_value(self, register_info, value=None):
        if register_info == 'msr':
            self.command('rm msr '+value,
                         error_message='Error setting register value')
            return
        target = self.targets[register_info['target']]
        if 'target_index' in register_info:
            target_index = register_info['target_index']
        else:
            target_index = 0
        if 'register_alias' in register_info:
            register_name = register_info['register_alias']
        else:
            register_name = register_info['register']
        register = target['registers'][register_info['register']]
        if value is None:
            value = register_info['injected_value']
        if 'type' in target and target['type'] == 'memory_mapped':
            command = 'mm'
            if 'bits' in register:
                bits = register['bits']
                if bits == 8:
                    command += 'b'
                elif bits == 16:
                    command += 'h'
                elif bits == 64:
                    command += 'd'
            address = target['base'][target_index] + register['offset']
            self.command(command+' '+hex(address)+' '+value+' 1',
                         error_message='Error getting register value')
        elif 'SPR' in register:
            self.command('rmspr '+str(register['SPR'])+' '+value,
                         error_message='Error setting register value')
        elif 'PMR' in register:
            self.command('rmpmr '+str(register['PMR'])+' '+value,
                         error_message='Error setting register value')
        else:
            self.command('rm '+register_name+' '+value,
                         error_message='Error setting register value')