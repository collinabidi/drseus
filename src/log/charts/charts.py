from django.db.models import Avg, Case, F, StdDev, TextField, Value, When
from django.db.models.functions import Concat, Length, Substr
from django.db.models import Max
from numpy import linspace

from . import create_chart


def overview(**kwargs):
    create_chart(chart_title='Overview',
                 xaxis_model='results',
                 pie=True,
                 **kwargs)


def outcomes_by_targets(**kwargs):
    create_chart(chart_title='Targets',
                 xaxis_title='Injected Target',
                 xaxis_name='Target',
                 xaxis_type='target',
                 log=True,
                 percent=True,
                 **kwargs)


def outcomes_by_target_indices(**kwargs):
    kwargs['injections'] = kwargs['injections'].annotate(target_name=Case(
        When(target_index__isnull=True, then=F('target')),
        default=Concat('target', Value('['),  'target_index', Value(']'),
                       output_field=TextField())))
    create_chart(chart_title='Targets (With Indices)',
                 xaxis_title='Injected Target',
                 xaxis_name='Target',
                 xaxis_type='target_name',
                 log=True,
                 percent=True,
                 **kwargs)


def data_diff_by_targets(**kwargs):
    create_chart(chart_title='Data Destruction By Target',
                 xaxis_title='Injected Target',
                 xaxis_name='Target',
                 xaxis_type='target',
                 yaxis_items=['Data Match'],
                 average='result__data_diff',
                 **kwargs)


def execution_time_by_targest(**kwargs):
    create_chart(chart_title='Average Execution Time By Target',
                 xaxis_title='Injected Target',
                 xaxis_name='Target',
                 xaxis_type='target',
                 yaxis_items=['Execution Time'],
                 average='result__execution_time',
                 **kwargs)


def outcomes_by_registers(**kwargs):
    kwargs['injections'] = kwargs['injections'].exclude(target='TLB')
    create_chart(chart_title='Registers',
                 xaxis_title='Injected Register',
                 xaxis_name='Register',
                 xaxis_type='register',
                 rotate_labels=True,
                 **kwargs)


def outcomes_by_register_fields(**kwargs):
    kwargs['injections'] = kwargs['injections'].exclude(
        target='TLB').exclude(field__isnull=True)
    create_chart(chart_title='Register Fields',
                 xaxis_title='Injected Register Field',
                 xaxis_name='Field',
                 xaxis_type='field',
                 rotate_labels=True,
                 **kwargs)


def outcomes_by_register_bits(**kwargs):
    kwargs['injections'] = kwargs['injections'].exclude(target='TLB')
    create_chart(chart_title='Register Bits',
                 xaxis_title='Injected Bit',
                 xaxis_name='Bit',
                 xaxis_type='bit',
                 **kwargs)


def outcomes_by_register_access(**kwargs):
    kwargs['injections'] = kwargs['injections'].exclude(
        target='TLB').exclude(register_access__isnull=True)
    create_chart(chart_title='Register Access',
                 xaxis_title='Injected Register Acces',
                 xaxis_name='Access',
                 xaxis_type='register_access',
                 **kwargs)


def outcomes_by_tlb_entries(**kwargs):
    kwargs['injections'] = kwargs['injections'].filter(target='TLB').annotate(
        temp=Concat('register', Value(':'), 'register_index',
                    output_field=TextField())).annotate(
        tlb_entry=Concat(Substr('temp', 1, Length('temp')-3), Value('}'),
                         output_field=TextField()))
    create_chart(chart_title='TLB Entries',
                 xaxis_title='Injected TLB Entry',
                 xaxis_name='Entry',
                 xaxis_type='tlb_entry',
                 rotate_labels=True,
                 **kwargs)


def outcomes_by_tlb_fields(**kwargs):
    kwargs['injections'] = kwargs['injections'].filter(target='TLB')
    create_chart(chart_title='TLB Fields',
                 xaxis_title='Injected TLB Field',
                 xaxis_name='Field',
                 xaxis_type='field',
                 rotate_labels=True,
                 **kwargs)


def outcomes_by_execution_times(**kwargs):
    kwargs['results'] = kwargs['results'].filter(returned=True).exclude(
        execution_time__isnull=True)
    avg = kwargs['results'].aggregate(
        Avg('execution_time'))['execution_time__avg']
    std_dev = kwargs['results'].aggregate(
        StdDev('execution_time'))['execution_time__stddev']
    execution_times = linspace(max(0, avg-(std_dev*3)), avg+(std_dev*3), 1000,
                               endpoint=False).tolist()
    create_chart(chart_title='Execution Times',
                 xaxis_title=(
                    'Execution Time (Seconds) for '
                    '(\u03bc-3\u03c3, \u03bc+3\u03c3), '
                    '\u03bc={:.2f} & \u03c3={:.2f}'.format(avg, std_dev)),
                 xaxis_name='Time',
                 xaxis_model='results',
                 xaxis_type='execution_time',
                 xaxis_items=execution_times,
                 smooth=True,
                 intervals=True,
                 **kwargs)


def outcomes_by_injection_times(**kwargs):
    kwargs['injections'] = kwargs['injections'].exclude(time__isnull=True)
    times = linspace(0,
                     kwargs['injections'].aggregate(Max('time'))['time__max'],
                     min(kwargs['injections'].count()/10, 1000),
                     endpoint=False).tolist()[1:]
    create_chart(chart_title='Injections Over Time',
                 xaxis_title='Injection Time (Seconds)',
                 xaxis_name='Time',
                 xaxis_type='time',
                 xaxis_items=times,
                 smooth=True,
                 intervals=True,
                 **kwargs)


def data_diff_by_injection_times(**kwargs):
    kwargs['injections'] = kwargs['injections'].exclude(time__isnull=True)
    times = linspace(0,
                     kwargs['injections'].aggregate(Max('time'))['time__max'],
                     min(kwargs['injections'].count()/10, 1000),
                     endpoint=False).tolist()[1:]
    create_chart(chart_title='Data Destruction Over Time',
                 xaxis_title='Injection Time (Seconds)',
                 xaxis_name='Time',
                 xaxis_type='time',
                 xaxis_items=times,
                 yaxis_items=['Data Diff'],
                 average='result__data_diff',
                 smooth=True,
                 intervals=True,
                 export_wide=True,
                 **kwargs)


def outcomes_by_checkpoint(**kwargs):
    kwargs['injections'] = kwargs['injections'].exclude(checkpoint__isnull=True)
    create_chart(chart_title='Injections Over Time',
                 xaxis_title='Injected Checkpoint',
                 xaxis_name='Checkpoint',
                 xaxis_type='checkpoint',
                 smooth=True,
                 **kwargs)


def data_diff_by_checkpoint(**kwargs):
    kwargs['injections'] = kwargs['injections'].exclude(checkpoint__isnull=True)
    create_chart(chart_title='Data Destruction Over Time',
                 xaxis_title='Injected Checkpoint',
                 xaxis_name='Checkpoint',
                 xaxis_type='checkpoint',
                 yaxis_items=['Data Diff'],
                 average='result__data_diff',
                 smooth=True,
                 **kwargs)


def outcomes_by_num_injections(**kwargs):
    kwargs['results'] = kwargs['results'].exclude(
        num_injections=0).exclude(num_injections__isnull=True)
    create_chart(chart_title='Injection Quantity',
                 xaxis_title='Injections Per Execution',
                 xaxis_name='Injections',
                 xaxis_model='results',
                 xaxis_type='num_injections',
                 **kwargs)


def register_propagation(**kwargs):
    kwargs['injections'] = kwargs['injections'].exclude(
        result__num_register_diffs__isnull=True)
    create_chart(chart_title='Fault Propagation (Registers)',
                 xaxis_title='Injection Target',
                 xaxis_name='Target',
                 xaxis_type='target',
                 yaxis_items=['Registers'],
                 average='result__num_register_diffs',
                 **kwargs)


def memory_propagation(**kwargs):
    kwargs['injections'] = kwargs['injections'].exclude(
        result__num_memory_diffs__isnull=True)
    create_chart(chart_title='Fault Propagation (Memory Blocks)',
                 xaxis_title='Injection Target',
                 xaxis_name='Target',
                 xaxis_type='target',
                 yaxis_items=['Memory Blocks'],
                 average='result__num_memory_diffs',
                 **kwargs)