"""
Copyright (c) 2018 NSF Center for Space, High-performance, and Resilient Computing (SHREC)
University of Pittsburgh. All rights reserved.

Redistribution and use in source and binary forms, with or without modification, are permitted provided
that the following conditions are met:
1. Redistributions of source code must retain the above copyright notice,
   this list of conditions and the following disclaimer.
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS AS IS AND ANY EXPRESS OR IMPLIED WARRANTIES, 
INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. 
IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR 
CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT 
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY
OF SUCH DAMAGE.
"""

# TODO: add ETSEC_TBI and Security targets to P2020

# if count is not present it is assumed to be 1
# if bits is not present it is assumbed to be 32

# p2020_ccsrbar = 0xFFE00000

# RAZ: Read-As-Zero
# WI: Write-ignored
# RAO: Read-As-One
# RAZ/WI: Read-As-Zero, Writes Ignored
# RAO/SBOP: Read-As-One, Should-Be-One-or-Preserved on writes.
# RAO/WI: Read-As-One, Writes Ignored
# RAZ/SBZP: Read-As-Zero, Should-Be-Zero-or-Preserved on writes
# SBO: Should-Be-One
# SBOP: Should-Be-One-or-Preserved
# SBZ: Should-Be-Zero
# SBZP: Should-Be-Zero-or-Preserved


# TODO: cache opposite tag?
# TODO: cache tag should be less than 64 bits

from json import dump, load
from os.path import abspath, dirname, join
from random import choice, randrange

directory = dirname(abspath(__file__))


def load_targets(architecture, type_):
    with open(join(directory, architecture, '{}.json'.format(type_)), 'r') \
            as json_file:
        targets = load(json_file)
    return targets


def save_targets(architecture, type_, targets):
    with open(join(directory, architecture, '{}.json'.format(type_)), 'w') \
            as json_file:
        dump(targets, json_file, indent=4, sort_keys=True)


def calculate_target_bits(targets):
    for target in targets:
        # count bits for each target
        total_bits = 0
        for register in targets[target]['registers']:
            if 'bits' in targets[target]['registers'][register]:
                bits = (targets[target]['registers'][register]
                               ['bits'])
            elif 'type' in targets[target] and \
                    targets[target]['type'] in ['gcache', 'tlb']:
                bits = 0
                for field in (targets[target]['registers'][register]
                                     ['fields']).values():
                    bits += field['bits']
            else:
                bits = 32
            if 'count' in targets[target]['registers'][register]:
                count = 1
                if 'type' in targets[target] and \
                        targets[target]['type'] in ['gcache', 'tlb']:
                    dimensions = (targets[target]['registers']
                                         [register]['count'][:-1])
                else:
                    dimensions = (targets[target]['registers']
                                         [register]['count'])
                for dimension in dimensions:
                    count *= dimension
            else:
                count = 1
            (targets[target]['registers']
                    [register]['total_bits']) = count * bits
            total_bits += count * bits
            # if a register is partially implemented generate an adjust_bit
            # mapping list to ensure an unimplemented field is not injected
            if 'partial' in targets[target]['registers'][register] \
                and (targets[target]['registers'][register]
                            ['partial']):
                adjust_bit = []
                if 'type' in targets[target] and \
                        targets[target]['type'] == 'tlb':
                    for field_range in (targets[target]['registers'][register]
                                               ['fields'].values()):
                        adjust_bit.extend(range(field_range[0],
                                                field_range[1]+1))
                else:
                    for field in (targets[target]['registers'][register]
                                         ['fields']):
                        try:
                            adjust_bit.extend(range(field[1][0], field[1][1]+1))
                        except:
                            print(field)
                if len(adjust_bit) != bits:
                    raise Exception(
                        'Bits mismatch for register: {} in target: {}'.format(
                            register, target))
                else:
                    (targets[target]['registers'][register]
                            ['adjust_bit']) = sorted(adjust_bit)
        if 'count' in targets[target]:
            total_bits *= targets[target]['count']
        targets[target]['total_bits'] = total_bits


def get_targets(architecture, type_, selected_targets, selected_registers,
                caches=True):  # caches only matter for simics campaigns
    targets = load_targets('', architecture)
    targets_info = targets[type_]
    targets = targets['targets']
    if not caches:
        if 'unused_targets' not in targets_info:
            targets_info['unused_targets'] = []
        for target in targets:
            if 'type' in targets[target] and \
                    targets[target]['type'] == 'gcache':
                targets_info['unused_targets'].append(target)
    if selected_targets is not None:
        temp = selected_targets
        selected_targets = []
        for target in temp:
            selected_targets.append(target.lower())
        invalid_targets = []
        for selected_target in selected_targets:
            for target in targets:
                if target.lower() == selected_target:
                    break
            else:
                invalid_targets.append(selected_target)
        if invalid_targets:
            raise Exception('invalid selected targets: {}'.format(
                ', '.join(invalid_targets)))
        if 'unused_targets' not in targets_info:
            targets_info['unused_targets'] = []
        for target in targets:
            if target not in targets_info['unused_targets'] and \
                    target.lower() not in selected_targets:
                targets_info['unused_targets'].append(target)
    if 'unused_targets' in targets_info:
        for target in targets_info['unused_targets']:
            del targets[target]
            if target in targets_info['targets']:
                del targets_info['targets'][target]
    if selected_registers is not None:
        temp = selected_registers
        selected_registers = []
        for register in temp:
            selected_registers.append(register.lower())
        invalid_registers = []
        for selected_register in selected_registers:
            for target in targets:
                found = False
                for register in targets[target]['registers']:
                    if register.lower() == selected_register:
                        found = True
                        break
                if found:
                    break
            else:
                invalid_registers.append(selected_register)
        if invalid_registers:
            raise Exception('invalid selected registers: {}'.format(
                ', '.join(invalid_registers)))
        if 'unused_targets' not in targets_info:
            targets_info['unused_targets'] = []
        for target in targets:
            if target not in targets_info['targets']:
                targets_info['targets'][target] = {}
            if 'unused_registers' not in targets_info['targets'][target]:
                targets_info['targets'][target]['unused_registers'] = {}
            for register in targets[target]['registers']:
                if register.lower() not in selected_registers:
                    (targets_info['targets'][target]
                                 ['unused_registers'][register]) = {}
    empty_targets = []
    for target_name, target in targets.items():
        if target_name in targets_info['targets']:
            target_info = targets_info['targets'][target_name]
            if 'unused_registers' in target_info:
                for register_name in target_info['unused_registers']:
                    del target['registers'][register_name]
            for register_name, register in target['registers'].items():
                if 'registers' in target_info and \
                        register_name in target_info['registers']:
                    register_info = target_info['registers'][register_name]
                    if 'unused_fields' in register_info:
                        bits = 0
                        fields = []
                        for field in register['fields']:
                            if field[0] not in register_info['unused_fields']:
                                fields.append(field)
                                bits += (field[1][1] - field[1][0]) + 1
                        register['fields'] = fields
                        register['partial'] = True
                        del register_info['unused_fields']
                        if 'bits' in register:
                            register['actual_bits'] = register['bits']
                        else:
                            register['actual_bits'] = 32
                        register['bits'] = bits
                    register.update(register_info)
            if 'registers' in target_info:
                del target_info['registers']
            if 'unused_registers' in target_info:
                del target_info['unused_registers']
            target.update(target_info)
        if len(target['registers']) == 0:
            empty_targets.append(target_name)
    for target in empty_targets:
        del targets[target]
    calculate_target_bits(targets)
    return targets


def choose_injection(targets, selected_target_indices):
    injection = {}
    target_list = []
    total_bits = 0
    for target in targets:
        bits = targets[target]['total_bits']
        target_list.append((target, bits))
        total_bits += bits
    random_bit = randrange(total_bits)
    bit_sum = 0
    for target in target_list:
        bit_sum += target[1]
        if random_bit < bit_sum:
            injection['target'] = target[0]
            target = targets[target[0]]
            break
    else:
        raise Exception('Error choosing injection target')
    if 'count' in target and target['count'] > 1:
        if selected_target_indices is None:
            injection['target_index'] = randrange(target['count'])
        else:
            indices = []
            for index in range(target['count']):
                if index in selected_target_indices:
                    indices.append(index)
            if indices:
                injection['target_index'] = choice(indices)
            else:
                raise Exception('invalid selected target indices')
    if 'target_index' in injection:
        injection['target_name'] = '{}[{}]'.format(injection['target'],
                                                   injection['target_index'])
    else:
        injection['target_name'] = injection['target']
    register_list = []
    total_bits = 0
    for register in target['registers']:
        bits = target['registers'][register]['total_bits']
        register_list.append((register, bits))
        total_bits += bits
    random_bit = randrange(total_bits)
    bit_sum = 0
    for register in register_list:
        bit_sum += register[1]
        if random_bit < bit_sum:
            injection['register'] = register[0]
            register = target['registers'][register[0]]
            break
    else:
        raise Exception('Error choosing register for target: {}'.format(
            injection['target']))
    if 'count' in register:
        injection['register_index'] = []
        for dimension in register['count']:
            index = randrange(dimension)
            injection['register_index'].append(index)
    if 'alias' in register:
        injection['register_alias'] = register['alias']['register']
        if 'register_index' in register['alias']:
            injection['register_index'] = register['alias']['register_index']
    if 'type' in target and target['type'] == 'tlb':
        fields_list = []
        total_bits = 0
        for field in register['fields']:
            bits = register['fields'][field]['bits']
            fields_list.append((field, bits))
            total_bits += bits
        random_bit = randrange(total_bits)
        bit_sum = 0
        for field in fields_list:
            bit_sum += field[1]
            if random_bit < bit_sum:
                injection['field'] = field[0]
                field = register['fields'][field[0]]
                break
        else:
            raise Exception('Error choosing TLB field to inject')
        if 'split' in field and field['split']:
            total_bits = field['bits_h'] + field['bits_l']
            random_bit = randrange(total_bits)
            if random_bit < field['bits_l']:
                injection['register_index'][-1] = field['index_l']
                start_bit_index = field['bit_indicies_l'][0]
                end_bit_index = field['bit_indicies_l'][1]
            else:
                injection['register_index'][-1] = field['index_h']
                start_bit_index = field['bit_indicies_h'][0]
                end_bit_index = field['bit_indicies_h'][1]
        else:
            injection['register_index'][-1] = field['index']
            start_bit_index = field['bit_indicies'][0]
            end_bit_index = field['bit_indicies'][1]
        injection['bit'] = randrange(start_bit_index, end_bit_index+1)
        injection['tlb_entry'] = injection['register']
        for index in injection['register_index'][:-1]:
            injection['tlb_entry'] += '[{}]'.format(index)
    elif 'type' in target and target['type'] == 'gcache':
        pass
        fields_list = []
        total_bits = 0
        for field in register['fields']:
            bits = register['fields'][field]['bits']
            fields_list.append((field, bits))
            total_bits += bits
        random_bit = randrange(total_bits)
        bit_sum = 0
        for field in fields_list:
            bit_sum += field[1]
            if random_bit < bit_sum:
                injection['field'] = field[0]
                field = register['fields'][field[0]]
                break
        else:
            raise Exception('Error choosing cache field to inject')
        injection['register_index'][-1] = field['index']
        injection['bit'] = randrange(field['bits'])
    else:
        if 'bits' in register:
            injection['bit'] = randrange(register['bits'])
        else:
            injection['bit'] = randrange(32)
        if 'adjust_bit' in register:
            injection['bit'] = register['adjust_bit'][injection['bit']]
        if 'fields' in register:
            for field in register['fields']:
                if injection['bit'] in range(field[1][0], field[1][1]+1):
                    injection['field'] = field[0]
                    break
            else:
                raise Exception(
                    'Error finding register field name for target: {}, '
                    'register: {}, bit: {}'.format(injection['target'],
                                                   injection['register'],
                                                   injection['bit']))
    return injection


def get_num_bits(field, register, target, targets):
    register = targets[target]['registers'][register]
    if 'type' in targets[target] and targets[target]['type'] == 'gcache':
        num_bits = register['fields'][field]['bits']
    elif 'actual_bits' in register:
        num_bits = register['actual_bits']
    elif 'bits' in register:
        num_bits = register['bits']
    else:
        num_bits = 32
    return num_bits
