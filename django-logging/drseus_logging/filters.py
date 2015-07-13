import re
from django import forms
import django_filters
from .models import (result, hw_injection, simics_injection,
                     simics_register_diff)


def fix_sort(string):
    return ''.join([text.zfill(5) if text.isdigit() else text.lower() for
                    text in re.split('([0-9]+)', str(string[0]))])


class hw_result_filter(django_filters.FilterSet):
    def hw_injection_choices(attribute):
        choices = []
        for item in sorted(hw_injection.objects.values(attribute).distinct()):
            choices.append((item[attribute], item[attribute]))
        return sorted(choices, key=fix_sort)

    def hw_result_choices(attribute):
        choices = []
        for item in sorted(result.objects.values(attribute).distinct()):
            choices.append((item[attribute], item[attribute]))
        return sorted(choices, key=fix_sort)

    injection__core = django_filters.MultipleChoiceFilter(
        choices=hw_injection_choices('core'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(hw_injection_choices('core'))),
            'style': 'width:100%;'
        })
    )
    injection__register = django_filters.MultipleChoiceFilter(
        choices=hw_injection_choices('register'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(hw_injection_choices('register')) if
                        len(hw_injection_choices('register')) < 20 else '20'),
            'style': 'width:100%;'
        })
    )
    injection__bit = django_filters.MultipleChoiceFilter(
        choices=hw_injection_choices('bit'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(hw_injection_choices('bit')) if
                        len(hw_injection_choices('bit')) < 20 else '20'),
            'style': 'width:100%;'
        })
    )
    outcome = django_filters.MultipleChoiceFilter(
        choices=hw_result_choices('outcome'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(hw_result_choices('outcome'))),
            'style': 'width:100%;'
        })
    )

    class Meta:
        model = result
        fields = ['injection__core', 'injection__register', 'injection__bit',
                  'outcome']


class simics_result_filter(django_filters.FilterSet):
    def simics_injection_choices(attribute):
        choices = []
        for item in sorted(
                simics_injection.objects.values(attribute).distinct()):
            choices.append((item[attribute], item[attribute]))
        return sorted(choices, key=fix_sort)

    def simics_result_choices(attribute):
        choices = []
        for item in sorted(result.objects.values(attribute).distinct()):
            choices.append((item[attribute], item[attribute]))
        return sorted(choices, key=fix_sort)

    outcome_category = django_filters.MultipleChoiceFilter(
        choices=simics_result_choices('outcome_category'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_result_choices('outcome_category'))),
            'style': 'width:100%;'
        })
    )
    outcome = django_filters.MultipleChoiceFilter(
        choices=simics_result_choices('outcome'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_result_choices('outcome'))),
            'style': 'width:100%;'
        })
    )
    simics_injection__target = django_filters.MultipleChoiceFilter(
        choices=simics_injection_choices('target'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_injection_choices('target'))),
            'style': 'width:100%;'
        })
    )
    simics_injection__target_index = django_filters.MultipleChoiceFilter(
        choices=simics_injection_choices('target_index'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_injection_choices('target_index'))),
            'style': 'width:100%;'
        })
    )
    simics_injection__register = django_filters.MultipleChoiceFilter(
        choices=simics_injection_choices('register'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_injection_choices('register'))),
            'style': 'width:100%;'
        })
    )
    simics_injection__register_index = django_filters.MultipleChoiceFilter(
        choices=simics_injection_choices('register_index'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_injection_choices('register_index')) if
                        len(simics_injection_choices('register_index')) < 20
                        else '20'),
            'style': 'width:100%;'
        })
    )
    simics_injection__bit = django_filters.MultipleChoiceFilter(
        choices=simics_injection_choices('bit'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_injection_choices('bit')) if
                        len(simics_injection_choices('bit')) < 20 else '20'),
            'style': 'width:100%;'
        })
    )

    class Meta:
        model = result
        exclude = ['iteration', 'dut_output', 'aux_output', 'debugger_output',
                   'paramiko_output', 'aux_paramiko_output', 'data_diff',
                   'detected_errors']


class simics_injection_filter(django_filters.FilterSet):
    def simics_injection_choices(attribute):
        choices = []
        for item in sorted(
                simics_injection.objects.values(attribute).distinct()):
            choices.append((item[attribute], item[attribute]))
        return sorted(choices, key=fix_sort)

    def simics_result_choices(attribute):
        choices = []
        for item in sorted(result.objects.values(attribute).distinct()):
            choices.append((item[attribute], item[attribute]))
        return sorted(choices, key=fix_sort)

    result__outcome_category = django_filters.MultipleChoiceFilter(
        choices=simics_result_choices('outcome_category'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_result_choices('outcome_category'))),
            'style': 'width:100%;'
        })
    )
    result__outcome = django_filters.MultipleChoiceFilter(
        choices=simics_result_choices('outcome'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_result_choices('outcome'))),
            'style': 'width:100%;'
        })
    )
    target = django_filters.MultipleChoiceFilter(
        choices=simics_injection_choices('target'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_injection_choices('target'))),
            'style': 'width:100%;'
        })
    )
    target_index = django_filters.MultipleChoiceFilter(
        choices=simics_injection_choices('target_index'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_injection_choices('target_index'))),
            'style': 'width:100%;'
        })
    )
    register = django_filters.MultipleChoiceFilter(
        choices=simics_injection_choices('register'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_injection_choices('register'))),
            'style': 'width:100%;'
        })
    )
    register_index = django_filters.MultipleChoiceFilter(
        choices=simics_injection_choices('register_index'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_injection_choices('register_index')) if
                        len(simics_injection_choices('register_index')) < 20
                        else '20'),
            'style': 'width:100%;'
        })
    )
    bit = django_filters.MultipleChoiceFilter(
        choices=simics_injection_choices('bit'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_injection_choices('bit')) if
                        len(simics_injection_choices('bit')) < 20 else '20'),
            'style': 'width:100%;'
        })
    )

    class Meta:
        model = simics_injection
        exclude = ['result', 'injection_number', 'gold_value', 'injected_value',
                   'checkpoint_number', 'config_object', 'config_type', 'field']


class simics_register_diff_filter(django_filters.FilterSet):
    def simics_register_diff_choices(attribute):
        choices = []
        for item in sorted(
                simics_register_diff.objects.values(attribute).distinct()):
            choices.append((item[attribute], item[attribute]))
        return sorted(choices, key=fix_sort)

    checkpoint_number = django_filters.MultipleChoiceFilter(
        choices=simics_register_diff_choices('checkpoint_number'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_register_diff_choices(
                            'checkpoint_number')) if
                        len(simics_register_diff_choices(
                            'checkpoint_number')) < 30 else '30'),
            'style': 'width:100%;'
        })
    )
    register = django_filters.MultipleChoiceFilter(
        choices=simics_register_diff_choices('register'),
        widget=forms.SelectMultiple(attrs={
            'size': str(len(simics_register_diff_choices('register')) if
                        len(simics_register_diff_choices('register')) < 30
                        else '30'),
            'style': 'width:100%;'
        })
    )

    class Meta:
        model = simics_register_diff
        fields = ['checkpoint_number', 'register']
