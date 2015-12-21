from __future__ import print_function
from datetime import datetime
import pyudev
from telnetlib import Telnet
from termcolor import colored
from threading import Thread
import time
import random
from signal import SIGINT
import socket
import sqlite3
import subprocess

from dut import dut
from error import DrSEUsError
from sql import insert_dict

# zedboards[uart_serial] = ftdi_serial
zedboards = {'844301CF3718': '210248585809',
             '8410A3D8431C': '210248657631',
             '036801551E13': '210248691084'}


def find_ftdi_serials():
    context = pyudev.Context()
    debuggers = context.list_devices(ID_VENDOR_ID='0403', ID_MODEL_ID='6014')
    serials = []
    for debugger in debuggers:
        if 'DEVLINKS' not in debugger:
            serials.append(debugger['ID_SERIAL_SHORT'])
    return serials


def find_uart_serials():
    context = pyudev.Context()
    uarts = context.list_devices(ID_VENDOR_ID='04b4', ID_MODEL_ID='0008')
    serials = {}
    for uart in uarts:
        if 'DEVLINKS' in uart:
            serials[uart['DEVNAME']] = uart['ID_SERIAL_SHORT']
    return serials


def find_open_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


class jtag:
    def __init__(self, ip_address, port, rsakey, dut_serial_port,
                 aux_serial_port, use_aux, dut_prompt, aux_prompt, debug,
                 timeout, campaign_number):
        self.ip_address = ip_address
        self.port = port
        self.timeout = 30
        self.debug = debug
        self.use_aux = use_aux
        self.output = ''
        try:
            self.telnet = Telnet(self.ip_address, self.port,
                                 timeout=self.timeout)
        except:
            self.telnet = None
            print('Could not connect to debugger, '
                  'running in supervisor-only mode')
        else:
            self.command('', error_message='Debugger not ready')
        self.dut = dut(rsakey, dut_serial_port, dut_prompt, debug, timeout,
                       campaign_number)
        if self.use_aux:
            self.aux = dut(rsakey, aux_serial_port, aux_prompt, debug, timeout,
                           campaign_number, color='cyan')
        # else:
        #     self.aux = None

    def __str__(self):
        string = ('JTAG Debugger at '+self.ip_address+' port '+str(self.port))
        return string

    def close(self):
        if self.telnet:
            self.telnet.close()
        self.dut.close()
        if self.use_aux:
            self.aux.close()

    def reset_dut(self, expected_output):
        if self.telnet:
            self.command('reset', expected_output, 'Error resetting DUT')
        else:
            self.dut.serial.write('\x03')
        self.dut.do_login()

    def time_application(self, command, aux_command, iterations, kill_dut):
        start = time.time()
        for i in xrange(iterations):
            if self.use_aux:
                aux_process = Thread(target=self.aux.command,
                                     args=('./'+aux_command, ))
                aux_process.start()
            self.dut.serial.write(str('./'+command+'\n'))
            if self.use_aux:
                aux_process.join()
            if kill_dut:
                self.dut.serial.write('\x03')
            self.dut.read_until()
        end = time.time()
        return (end - start) / iterations, None

    def inject_fault(self, result_id, iteration, injection_times, command,
                     selected_targets):
        if selected_targets is None:
            registers = self.registers
        else:
            registers = []
            for register in self.registers:
                for target in selected_targets:
                    if target in register:
                        registers.append(register)
                        break
        for injection in xrange(1, len(injection_times)+1):
            injection_data = {'result_id': result_id,
                              'injection_number': injection,
                              'time': injection_times[injection-1],
                              'timestamp': datetime.now()}
            if self.debug:
                print(colored('injection time: '+str(injection_data['time']),
                              'magenta'))
            if injection == 1:
                self.dut.serial.write(str('./'+command+'\n'))
            else:
                self.continue_dut()
            time.sleep(injection_data['time'])
            self.halt_dut()
            injection_data['core'] = random.randrange(2)
            self.select_core(injection_data['core'])
            injection_data['register'] = random.choice(self.registers)
            injection_data['gold_value'] = self.get_register_value(
                injection_data['register'])
            num_bits = len(injection_data['gold_value'].replace('0x', '')) * 4
            injection_data['bit'] = random.randrange(num_bits)
            injection_data['injected_value'] = '0x%x' % (
                int(injection_data['gold_value'], base=16)
                ^ (1 << injection_data['bit']))
            if self.debug:
                print(colored('core: '+str(injection_data['core']), 'magenta'))
                print(colored('register: '+injection_data['register'],
                              'magenta'))
                print(colored('bit: '+str(injection_data['bit']), 'magenta'))
                print(colored('gold value: '+injection_data['gold_value'],
                              'magenta'))
                print(colored('injected value: ' +
                              injection_data['injected_value'], 'magenta'))
            self.set_register_value(injection_data['register'],
                                    injection_data['injected_value'])
            sql_db = sqlite3.connect('campaign-data/db.sqlite3', timeout=60)
            sql = sql_db.cursor()
            insert_dict(sql, 'injection', injection_data)
            sql.execute('DELETE FROM log_injection WHERE '
                        'result_id=? AND injection_number=0', (result_id,))
            sql_db.commit()
            sql_db.close()
            if int(injection_data['injected_value'], base=16) != int(
                    self.get_register_value(injection_data['register']),
                    base=16):
                raise DrSEUsError('Error injecting fault')


class bdi(jtag):
    error_messages = ['timeout while waiting for halt',
                      'wrong state for requested command', 'read access failed']

    def __init__(self, ip_address, rsakey, dut_serial_port, aux_serial_port,
                 use_aux, dut_prompt, aux_prompt, debug, timeout,
                 campaign_number):
        jtag.__init__(self, ip_address, 23, rsakey, dut_serial_port,
                      aux_serial_port, use_aux, dut_prompt, aux_prompt, debug,
                      timeout, campaign_number)

    def __str__(self):
        string = 'BDI3000 at '+self.ip_address+' port '+str(self.port)
        return string

    def close(self):
        if self.telnet:
            self.telnet.write('quit\r')
        jtag.close(self)

    def command(self, command, expected_output=[], error_message=None):
        return_buffer = ''
        if error_message is None:
            error_message = command
        buff = self.telnet.read_very_lazy()
        self.output += buff
        if self.debug:
            print(colored(buff, 'yellow'))
        if command:
            command = command+'\r'
            self.telnet.write(command)
            self.telnet.write('\r')
            self.output += command
            if self.debug:
                print(colored(command, 'yellow'))
        for i in xrange(len(expected_output)):
            index, match, buff = self.telnet.expect(expected_output,
                                                    timeout=self.timeout)
            self.output += buff
            return_buffer += buff
            if self.debug:
                print(colored(buff, 'yellow'), end='')
            if index < 0:
                raise DrSEUsError(error_message)
        else:
            if self.debug:
                print()
        index, match, buff = self.telnet.expect(self.prompts,
                                                timeout=self.timeout)
        self.output += buff
        return_buffer += buff
        if self.debug:
            print(colored(buff, 'yellow'))
        if index < 0:
            raise DrSEUsError(error_message)
        for message in self.error_messages:
            if message in buff:
                raise DrSEUsError(error_message)
        return return_buffer


class bdi_arm(bdi):
    # BDI3000 with ZedBoard requires Linux kernel <= 3.6.0 (Xilinx TRD14-4)
    def __init__(self, ip_address, rsakey, dut_serial_port, aux_serial_port,
                 use_aux, dut_prompt, aux_prompt, debug, timeout,
                 campaign_number):
        self.prompts = ['A9#0>', 'A9#1>']
        # TODO: ttb1 cannot inject into bits 2, 8, 9, 11
        self.registers = ['r0', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8',
                          'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'pc', 'cpsr',
                          # 'spsr', 'mainid', 'cachetype', 'tcmstatus',
                          # 'tlbtype', 'mputype', 'multipid', 'procfeature0',
                          # 'procfeature1', 'dbgfeature0', auxfeature0',
                          # 'memfeature0', 'memfeature1', 'memfeature2',
                          # 'memfeature3', 'instrattr0', 'instrattr1',
                          # 'instrattr2', 'instrattr3', 'instrattr4',
                          # 'instrattr5', 'instrattr6', 'instrattr7', 'control',
                          # 'auxcontrol', 'cpaccess', 'securecfg', 'securedbg',
                          # 'nonsecure',
                          'ttb0', 'ttb1',  # 'ttbc',
                          'dac',  # 'dfsr', 'ifsr', 'dauxfsr', 'iaucfsr',
                          'dfar', 'ifar',  # 'fcsepid',
                          'context'
                          ]
        bdi.__init__(self, ip_address, rsakey, dut_serial_port, aux_serial_port,
                     use_aux, dut_prompt, aux_prompt, debug, timeout,
                     campaign_number)

    def reset_dut(self):
        jtag.reset_dut(self, ['- TARGET: processing reset request',
                              '- TARGET: BDI removes TRST',
                              '- TARGET: Bypass check',
                              '- TARGET: JTAG exists check passed',
                              '- Core#0: ID code', '- Core#0: DP-CSW',
                              '- Core#0: DBG-AP', '- Core#0: DIDR',
                              '- Core#1: ID code', '- Core#1: DP-CSW',
                              '- Core#1: DBG-AP', '- Core#1: DIDR',
                              '- TARGET: BDI removes RESET',
                              '- TARGET: BDI waits for RESET inactive',
                              '- TARGET: Reset sequence passed',
                              '- TARGET: resetting target passed',
                              '- TARGET: processing target startup',
                              '- TARGET: processing target startup passed'])

    def halt_dut(self):
        self.command('halt 3', ['- TARGET: core #0 has entered debug mode',
                                '- TARGET: core #1 has entered debug mode'],
                     'Error halting DUT')

    def continue_dut(self):
        self.command('cont 3', error_message='Error continuing DUT')

    def select_core(self, core):
        # TODO: check if cores are running (not in debug mode)
        self.command('select '+str(core), ['Core number', 'Core state',
                                           'Debug entry cause', 'Current PC',
                                           'Current CPSR'],
                     'Error selecting core')

    def get_register_value(self, register):
        buff = self.command('rd '+register, [':'],
                            error_message='Error getting register value')
        return buff.split('\r')[0].split(':')[1].strip().split(' ')[0].strip()

    def set_register_value(self, register, value):
        self.command('rm '+register+' '+value, error_message='Error setting '
                                                             'register value')

    # def get_dut_regs(self, selected_targets):
    #     # TODO: get GPRs
    #     # TODO: check for unused registers ttbc? iaucfsr?
    #     regs = [{}, {}]
    #     for core in xrange(2):
    #         self.select_core(core)
    #         debug_reglist = self.command('rdump')
    #         for line in debug_reglist.split('\r')[:-1]:
    #             line = line.split(': ')
    #             register = line[0].strip()
    #             if selected_targets is None:
    #                 value = line[1].split(' ')[0].strip()
    #                 regs[core][register] = value
    #             else:
    #                 for target in selected_targets:
    #                     if target in register:
    #                         value = line[1].split(' ')[0].strip()
    #                         regs[core][register] = value
    #                         break
    #     return regs


class bdi_p2020(bdi):
    def __init__(self, ip_address, rsakey, dut_serial_port, aux_serial_port,
                 use_aux, dut_prompt, aux_prompt, debug, timeout,
                 campaign_number):
        self.prompts = ['P2020>']
        # TODO: add pmr, spr, L2 TLB
        # TODO: check if only certain bits are read only (some partially worked)
        # TODO: ccsrbar, tsr reset after read/write?
        self.registers = ['bbear', 'bbtar',  # 'altcar', 'altcbar', 'autorstsr',
                          # 'bptr', 'br0', 'br1', 'br2',
                          'br3',  # 'br4',
                          'br5',  # 'br6',
                          'br7',  # 'bucsr',
                          'cap_addr',  # 'cap_attr',
                          'cap_data_hi', 'cap_data_lo', 'cap_ecc',
                          # 'cap_ext_addr', 'ccsrbar', 'clkocr', 'cs0_bnds',
                          # 'cs0_config', 'cs0_config_2', 'cs1_bnds',
                          # 'cs1_config', 'cs1_config_2', 'cs2_bnds',
                          # 'cs2_config', 'cs2_config_2', 'cs3_bnds',
                          # 'cs3_config', 'cs3_config_2',
                          'csrr0', 'csrr1', 'ctr', 'dac1',
                          'dac2',  # 'dbcr0',
                          'dbcr1', 'dbcr2',  # 'dbsr',
                          'ddr_cfg',  # 'ddr_cfg_2', 'ddr_clk_cntl',
                          'ddr_data_init', 'ddr_init_addr',  # 'ddr_init_eaddr',
                          # 'ddr_interval', 'ddr_ip_rev1', 'ddr_ip_rev2',
                          'ddr_mode', 'ddr_mode_2', 'ddr_mode_cntl',
                          # 'ddr_wrlvl_cntl', 'ddr_zq_cntl',
                          'ddrcdr_1',  # 'ddrcdr_2', 'ddrclkdr', 'ddrdsr_1',
                          # 'ddrdsr_2',
                          'dear',  # 'dec',
                          'decar',  # 'devdisr', 'ecc_err_inject', 'ecmcr',
                          # 'ectrstcr', 'eeatr', 'eebacr', 'eebpcr', 'eedr',
                          # 'eeer', 'eehadr', 'eeladr',
                          'egpr0', 'egpr1', 'egpr2', 'egpr3', 'egpr4', 'egpr5',
                          'egpr6', 'egpr7', 'egpr8', 'egpr9', 'egpr10',
                          'egpr11', 'egpr12', 'egpr13', 'egpr14', 'egpr15',
                          'egpr16', 'egpr17', 'egpr18', 'egpr19', 'egpr20',
                          'egpr21', 'egpr22', 'egpr23', 'egpr24', 'egpr25',
                          'egpr26', 'egpr27', 'egpr28', 'egpr29', 'egpr30',
                          'egpr31',  # 'eipbrr1', 'eipbrr2', 'err_detect',
                          # 'err_disable',
                          'err_inject_hi', 'err_inject_lo',  # 'err_int_en',
                          # 'err_sbe', 'esr', 'fbar', 'fbcr',
                          'fcr', 'fir',  # 'fmr', 'fpar', 'gpporcr', 'hid0',
                          # 'hid1',
                          'iac1', 'iac2',  # 'ivor0', 'ivor1', 'ivor2', 'ivor3',
                          # 'ivor4', 'ivor5', 'ivor6', 'ivor7', 'ivor8',
                          # 'ivor9', 'ivor10', 'ivor11', 'ivor12', 'ivor13',
                          # 'ivor14', 'ivor15', 'ivor32', 'ivor33', 'ivor34',
                          # 'ivor35', 'ivpr', 'l1cfg0', 'l1cfg1', 'l1csr0',
                          # 'l1csr1', 'l2captdatahi', 'l2captdatalo',
                          # 'l2captecc', 'l2cewar0', 'l2cewar1', 'l2cewar2',
                          # 'l2cewar3', 'l2cewarea0', 'l2cewarea1',
                          # 'l2cewarea2', 'l2cewarea3',
                          'l2cewcr0',  # 'l2cewcr1',
                          'l2cewcr2', 'l2cewcr3',
                          # 'l2ctl', 'l2erraddrh', 'l2erraddrl', 'l2errattr',
                          # 'l2errctl', 'l2errdet', 'l2errdis', 'l2errinjctl',
                          'l2errinjhi', 'l2errinjlo',
                          # 'l2errinten', 'l2srbar0', 'l2srbar1', 'l2srbarea0',
                          # 'l2srbarea1', 'laipbrr1', 'laipbrr2', 'lawar0',
                          # 'lawar1', 'lawar2', 'lawar3', 'lawar4', 'lawar5',
                          # 'lawar6', 'lawar7', 'lawar8', 'lawar9', 'lawar10',
                          # 'lawar11', 'lawbar0', 'lawbar1', 'lawbar2',
                          # 'lawbar3', 'lawbar4', 'lawbar5', 'lawbar6',
                          # 'lawbar7', 'lawbar8', 'lawbar9', 'lawbar10',
                          # 'lawbar11', 'lbcr', 'lbcvselcr', 'lcrr',
                          'lr',  # 'lsdmr', 'lsor', 'lsrt',
                          'ltear', 'lteatr',  # 'ltedr', 'lteir', 'ltesr',
                          # 'lurt',
                          'mamr', 'mar',  # 'mas0', 'mas1', 'mas2',
                          # 'mas3', 'mas4', 'mas6', 'mas7',
                          'mbmr',  # 'mcmr', 'mcpsumr', 'mcsr',
                          'mcsrr0',  # 'mcsrr1',
                          'mdr',  # 'mm_pvr', 'mm_svr',
                          # 'mmucfg', 'mmucsr0', 'mrtpr', 'or0',
                          # 'or1', 'or2', 'or3', 'or4', 'or5', 'or6', 'or7',
                          # 'pid', 'pid0', 'pid1', 'pid2',
                          'pir',  # 'porbmsr', 'pordbgmsr', 'pordevsr',
                          # 'porimpscr', 'porpllsr', 'powmgtcsr', 'pvr',
                          # 'rstcr', 'rstrscr',
                          'sp',  # 'spefscr',
                          'sprg0', 'sprg1', 'sprg2', 'sprg3', 'sprg4', 'sprg5',
                          'sprg6', 'sprg7',  # 'srdscr0', 'srdscr1', 'srdscr2',
                          'srr0', 'srr1',  # 'svr', 'tbl',
                          'tbu',  # 'tcr', 'timing_cfg_0',
                          'timing_cfg_1',  # 'timing_cfg_2', 'timing_cfg_3',
                          # 'timing_cfg_4', 'timing_cfg_5', 'tlb0cfg',
                          # 'tlb1cfg', 'tsr',
                          'usprg0',
                          # 'xer'
                          ]
        # egpr's have twice as many bits (64) as other registers (32)
        self.registers.extend(['egpr0', 'egpr1', 'egpr2', 'egpr3', 'egpr4',
                               'egpr5', 'egpr6', 'egpr7', 'egpr8', 'egpr9',
                               'egpr10', 'egpr11', 'egpr12', 'egpr13', 'egpr14',
                               'egpr15', 'egpr16', 'egpr17', 'egpr18', 'egpr19',
                               'egpr20', 'egpr21', 'egpr22', 'egpr23', 'egpr24',
                               'egpr25', 'egpr26', 'egpr27', 'egpr28', 'egpr29',
                               'egpr30', 'egpr31'])
        bdi.__init__(self, ip_address, rsakey, dut_serial_port, aux_serial_port,
                     use_aux, dut_prompt, aux_prompt, debug, timeout,
                     campaign_number)

    def reset_dut(self):
        jtag.reset_dut(self, ['- TARGET: processing user reset request',
                              '- BDI asserts HRESET',
                              '- Reset JTAG controller passed',
                              '- JTAG exists check passed',
                              '- IDCODE',
                              '- SVR',
                              '- PVR',
                              '- CCSRBAR',
                              '- BDI removes HRESET',
                              '- TARGET: resetting target passed',
                              # '- TARGET: processing target startup',
                              '- TARGET: processing target startup passed'])

    def halt_dut(self):
        self.command('halt 0; halt 1', ['Target CPU', 'Core state',
                                        'Debug entry cause', 'Current PC',
                                        'Current CR', 'Current MSR',
                                        'Current LR']*2, 'Error halting DUT')

    def continue_dut(self):
        self.command('go 0 1', error_message='Error continuing DUT')

    def select_core(self, core):
        self.command('select '+str(core), ['Target CPU', 'Core state',
                                           'Debug entry cause', 'Current PC',
                                           'Current CR', 'Current MSR',
                                           'Current LR', 'Current CCSRBAR'],
                     'Error selecting core')

    def get_register_value(self, register):
        buff = self.command('rd '+register, error_message='Error getting '
                                                          'register value')
        return buff.split('\r')[0].split(':')[1].strip().split(' ')[0].strip()

    def set_register_value(self, register, value):
        self.command('rm '+register+' '+value, error_message='Error setting '
                                                             'register value')

    # def get_registers(self, selected_targets):
    #     regs = [{}, {}]
    #     for core in xrange(2):
    #         self.select_core(core)
    #         debug_reglist = self.command('rdump',
    #                                      error_message='Error getting '
    #                                                    'register list')
    #         for line in debug_reglist.split('\r')[:-2]:
    #             line = line.split(':')
    #             register = line[0].strip()
    #             if selected_targets is None:
    #                 value = line[1].split(' ')[0].strip()
    #                 regs[core][register] = value
    #             else:
    #                 for target in selected_targets:
    #                     if target in register:
    #                         value = line[1].split(' ')[0].strip()
    #                         regs[core][register] = value
    #                         break
    #     return regs


class openocd(jtag):
    error_messages = ['Target not examined yet']

    def __init__(self, ip_address, rsakey, dut_serial_port, aux_serial_port,
                 use_aux, dut_prompt, aux_prompt, debug, timeout,
                 campaign_number):
        self.prompts = ['>']
        self.registers = ['r0', 'r1', 'r2', 'r3', 'r4', 'r5', 'r6', 'r7', 'r8',
                          'r9', 'r10', 'r11', 'r12',  'pc', 'cpsr', 'sp', 'lr']
        serial = zedboards[find_uart_serials()[dut_serial_port]]
        port = find_open_port()
        self.dev_null = open('/dev/null', 'w')
        self.openocd = subprocess.Popen(['openocd', '-c',
                                         'gdb_port 0; tcl_port 0; '
                                         'telnet_port '+str(port)+'; '
                                         'interface ftdi; '
                                         'ftdi_serial '+serial+';',
                                         '-f', 'openocd_zedboard.cfg'],
                                        stderr=self.dev_null)
        time.sleep(1)
        jtag.__init__(self, '127.0.0.1', port, rsakey, dut_serial_port,
                      aux_serial_port, use_aux, dut_prompt, aux_prompt, debug,
                      timeout, campaign_number)

    def __str__(self):
        string = 'OpenOCD at localhost port '+str(self.port)
        return string

    def close(self):
        if self.telnet:
            self.telnet.write('shutdown\n')
        jtag.close(self)
        self.openocd.send_signal(SIGINT)
        self.openocd.wait()
        self.dev_null.close()

    def command(self, command, expected_output=[], error_message=None):
        return_buffer = ''
        if error_message is None:
            error_message = command
        buff = self.telnet.read_very_lazy()
        self.output += buff
        if self.debug:
            print(colored(buff, 'yellow'))
        if command:
            self.telnet.write(command+'\n')
            index, match, buff = self.telnet.expect([command],
                                                    timeout=self.timeout)
            self.output += buff
            return_buffer += buff
            if self.debug:
                print(colored(buff, 'yellow'))
            if index < 0:
                raise DrSEUsError(error_message)
        for i in xrange(len(expected_output)):
            index, match, buff = self.telnet.expect(expected_output,
                                                    timeout=self.timeout)
            self.output += buff
            return_buffer += buff
            if self.debug:
                print(colored(buff, 'yellow'), end='')
            if index < 0:
                raise DrSEUsError(error_message)
        else:
            if self.debug:
                print()
        index, match, buff = self.telnet.expect(self.prompts,
                                                timeout=self.timeout)
        self.output += buff
        return_buffer += buff
        if self.debug:
            print(colored(buff, 'yellow'))
        if index < 0:
            raise DrSEUsError(error_message)
        for message in self.error_messages:
            if message in buff:
                raise DrSEUsError(error_message)
        return return_buffer

    def reset_dut(self):
        jtag.reset_dut(self,
                       ['JTAG tap: zynq.dap tap/device found: 0x4ba00477'])

    def halt_dut(self):
        self.command('halt',
                     # 'targets zynq.cpu0; halt; targets zynq.cpu1; halt;',
                     ['target state: halted',
                      'target halted in ARM state due to debug-request, '
                      'current mode:', 'cpsr:', 'MMU:']*2,
                     'Error halting DUT')

    def continue_dut(self):
        self.command('resume', error_message='Error continuing DUT')

    def select_core(self, core):
        self.command('targets zynq.cpu'+str(core),
                     error_message='Error selecting core')

    def get_register_value(self, register):
        buff = self.command('reg '+register, [':'],
                            error_message='Error getting register value')
        return buff.split('\n')[1].split(':')[1].strip().split(' ')[0].strip()

    def set_register_value(self, register, value):
        self.command('reg '+register+' '+value, error_message='Error setting '
                                                              'register value')