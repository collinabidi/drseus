from __future__ import print_function
from datetime import datetime
from django.core.management import execute_from_command_line as django_command
import multiprocessing
import os
import shutil
import signal
import sys

from fault_injector import fault_injector
from jtag import find_ftdi_serials, find_uart_serials, openocd
import simics_config
from sql import sql
from supervisor import supervisor


def print_zedboard_info():
    ftdis = find_ftdi_serials()
    uarts = find_uart_serials()
    print('Attached ZedBoard Information')
    print('FTDI JTAG device serial numbers: ')
    for serial in ftdis:
        print('\t'+serial)
    print('Cypress UART device serial numbers:')
    for uart, serial in uarts.iteritems():
        print('\t'+uart+': '+serial)


def list_campaigns():
    with sql(row_factory='row') as db:
        db.cursor.execute('SELECT id, application, architecture, use_simics '
                          'FROM log_campaign')
        campaign_list = db.cursor.fetchall()
    print('DrSEUs Campaigns:')
    print('Number\t\tApplication\t\tArchitecture\tSimics')
    for campaign in campaign_list:
        campaign = list(campaign)
        campaign[3] = bool(campaign[3])
        print('\t\t'.join([str(item) for item in campaign]))


def get_last_campaign():
    if os.path.exists('campaign-data/db.sqlite3'):
        with sql(row_factory='row') as db:
            db.cursor.execute('SELECT id FROM log_campaign '
                              'ORDER BY id DESC LIMIT 1')
            campaign_data = db.cursor.fetchone()
        if campaign_data is not None:
            return campaign_data['id']
        else:
            return 0


def get_campaign_data(campaign_number):
    with sql(row_factory='row') as db:
        db.cursor.execute('SELECT * FROM log_campaign WHERE id=?',
                          (campaign_number,))
        campaign_data = db.cursor.fetchone()
    if campaign_data is None:
        raise Exception('could not find campaign number '+str(campaign_number))
    return campaign_data


def backup_database():
    print('backing up database...', end='')
    db_backup = ('campaign-data/' +
                 '-'.join([str(unit).zfill(2)
                           for unit in datetime.now().timetuple()[:6]]) +
                 '.db.sqlite3')
    shutil.copyfile('campaign-data/db.sqlite3', db_backup)
    print('done')


def delete_results(campaign_number):
    backup_database()
    if os.path.exists('campaign-data/'+str(campaign_number)+'/results'):
        shutil.rmtree('campaign-data/'+str(campaign_number)+'/results')
        print('deleted results')
    if os.path.exists('campaign-data/db.sqlite3'):
        with sql() as db:
            db.cursor.execute('DELETE FROM log_simics_memory_diff WHERE '
                              'result_id IN (SELECT id FROM log_result WHERE '
                              'campaign_id=?)', (campaign_number,))
            db.cursor.execute('DELETE FROM log_simics_register_diff WHERE '
                              'result_id IN (SELECT id FROM log_result WHERE '
                              'campaign_id=?)', (campaign_number,))
            db.cursor.execute('DELETE FROM log_injection WHERE '
                              'result_id IN (SELECT id FROM log_result WHERE '
                              'campaign_id=?)', (campaign_number,))
            db.cursor.execute('DELETE FROM log_result WHERE campaign_id=?',
                              (campaign_number,))
            db.connection.commit()
        print('flushed database')
    if os.path.exists('simics-workspace/injected-checkpoints/' +
                      str(campaign_number)):
        shutil.rmtree('simics-workspace/injected-checkpoints/' +
                      str(campaign_number))
        print('deleted injected checkpoints')


def delete_campaign(campaign_number):
    delete_results(campaign_number)
    if os.path.exists('campaign-data/db.sqlite3'):
        with sql() as db:
            db.cursor.execute('DELETE FROM log_campaign WHERE id=?',
                              (campaign_number,))
            db.connection.commit()
        print('deleted campaign from database')
    if os.path.exists('campaign-data/'+str(campaign_number)):
        shutil.rmtree('campaign-data/'+str(campaign_number))
        print('deleted campaign data')
    if os.path.exists('simics-workspace/gold-checkpoints/' +
                      str(campaign_number)):
        shutil.rmtree('simics-workspace/gold-checkpoints/' +
                      str(campaign_number))
        print('deleted gold checkpoints')


def delete_all():
    if os.path.exists('simics-workspace/gold-checkpoints'):
        shutil.rmtree('simics-workspace/gold-checkpoints')
        print('deleted gold checkpoints')
    if os.path.exists('simics-workspace/injected-checkpoints'):
        shutil.rmtree('simics-workspace/injected-checkpoints')
        print('deleted injected checkpoints')
    if os.path.exists('campaign-data'):
        shutil.rmtree('campaign-data')
        print('deleted campaign data')


def create_campaign(options):
    if options.directory == 'fiapps':
        if not os.path.exists('fiapps'):
            os.system('./setup_apps.sh')
        if not os.path.exists('fiapps/'+options.application):
            os.system('cd fiapps/; make '+options.application)
    else:
        if not os.path.exits(options.directory):
            raise Exception('cannot find directory '+options.directory)
    if options.use_simics and not os.path.exists('simics-workspace'):
        os.system('./setup_simics_workspace.sh')
    if not os.path.exists('campaign-data/db.sqlite3'):
        if not os.path.exists(('campaign-data')):
            os.mkdir('campaign-data')
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "log.settings")
        django_command([sys.argv[0], 'migrate', '--run-syncdb'])
    campaign_data = {
        'application': options.application,
        'architecture': options.architecture,
        'aux_command': (options.aux_application if options.aux_application
                        else options.application) +
                       ((' '+options.aux_arguments) if options.aux_arguments
                        else ''),
        'aux_output': '',
        'command': options.application+((' '+options.arguments)
                                        if options.arguments else ''),
        'debugger_output': '',
        'dut_output': '',
        'kill_dut': options.kill_dut,
        'output_file': options.file,
        'timestamp': datetime.now(),
        'use_aux': options.use_aux,
        'use_aux_output': options.use_aux and options.use_aux_output,
        'use_simics': options.use_simics}
    with sql() as db:
        db.insert_dict('campaign', campaign_data)
        campaign_data['id'] = db.cursor.lastrowid
    campaign_directory = 'campaign-data/'+str(campaign_data['id'])
    if os.path.exists(campaign_directory):
        raise Exception('directory already exists: '
                        'campaign-data/'+str(campaign_data['id']))
    else:
        os.mkdir(campaign_directory)
    options.debug = True
    drseus = fault_injector(campaign_data, options)
    drseus.setup_campaign(options)
    print('\nsuccessfully setup campaign')


def get_injection_data(result_id):
    with sql(row_factory='row') as db:
        db.cursor.execute('SELECT * FROM log_injection INNER JOIN log_result '
                          'ON (log_injection.result_id=log_result.id) '
                          'WHERE log_result.id=?', (result_id,))
        injection_data = db.cursor.fetchall()
    injection_data = sorted(injection_data,
                            key=lambda x: x['checkpoint_number'])
    return injection_data


def perform_injections(campaign_data, options, iteration_counter,
                       interactive=False):
    drseus = fault_injector(campaign_data, options)

    # def interrupt_handler(signum, frame):
    #     drseus.log_result('Interrupted', 'Incomplete')
    #     if os.path.exists('campaign-data/results/' +
    #                       str(campaign_data['id'])+'/'+str(drseus.result_id)):
    #         shutil.rmtree('campaign-data/results/' +
    #                       str(campaign_data['id'])+'/'+str(drseus.result_id))
    #     if not drseus.campaign_data['use_simics']:
    #         drseus.debugger.continue_dut()
    #     drseus.debugger.close()
    #     if drseus.campaign_data['use_simics']:
    #         if os.path.exists('simics-workspace/injected-checkpoints/' +
    #                           str(campaign_data['id'])+'/' +
    #                           str(drseus.result_id)):
    #             shutil.rmtree('simics-workspace/injected-checkpoints/' +
    #                           str(campaign_data['id'])+'/' +
    #                           str(drseus.result_id))
    #     if not interactive:
    #         sys.exit()
    # signal.signal(signal.SIGINT, interrupt_handler)

    if options.selected_targets is not None:
        selected_targets = options.selected_targets.split(',')
    else:
        selected_targets = None
    drseus.inject_and_monitor(iteration_counter, options.num_injections,
                              selected_targets, options.compare_all)


def inject_campaign(options):
    processes = []

    # def interrupt_handler(signum, frame):
    #     for process in processes:
    #         os.kill(process.pid, signal.SIGINT)
    #     for process in processes:
    #         process.join()
    # signal.signal(signal.SIGINT, interrupt_handler)

    campaign_data = get_campaign_data(options.campaign_number)
    iteration_counter = multiprocessing.Value('L', options.injection_iterations)
    if options.num_processes > 1 and (campaign_data['use_simics'] or
                                      campaign_data['architecture'] == 'a9'):
        if not campaign_data['use_simics'] and \
                campaign_data['architecture'] == 'a9':
            zedboards = find_uart_serials().keys()
        for i in xrange(options.num_processes):
            if not campaign_data['use_simics'] and \
                    campaign_data['architecture'] == 'a9':
                if i < len(zedboards):
                    options.dut_serial_port = zedboards[i]
                else:
                    break
            process = multiprocessing.Process(
                target=perform_injections,
                args=(campaign_data, options, iteration_counter)
            )
            processes.append(process)
            process.start()
        for process in processes:
            process.join()
    else:
        options.debug = True
        perform_injections(campaign_data, options, iteration_counter)


def regenerate(options):
    campaign_data = get_campaign_data(options.campaign_number)
    if not campaign_data['use_simics']:
        raise Exception('This feature is only available for Simics campaigns')
    injection_data = get_injection_data(options.result_id)
    drseus = fault_injector(campaign_data, options)
    checkpoint = drseus.debugger.regenerate_checkpoints(
        options.result_id, campaign_data['cycles_between'], injection_data)
    drseus.debugger.launch_simics_gui(checkpoint)
    shutil.rmtree('simics-workspace/injected-checkpoints/' +
                  str(campaign_data['id'])+'/'+str(options.result_id))


def view_logs(args):
    try:
        port = int(args[0])
    except (IndexError, ValueError):
        port = 8000
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "log.settings")
    django_command([sys.argv[0], 'runserver', str(port)])


def update_checkpoint_dependencies(campaign_number):
    for checkpoint in os.listdir('simics-workspace/gold-checkpoints/' +
                                 str(campaign_number)):
        config = simics_config.read_configuration(
            'simics-workspace/gold-checkpoints/' +
            str(campaign_number)+'/'+checkpoint)
        os.rename('simics-workspace/gold-checkpoints/' +
                  str(campaign_number)+'/'+checkpoint+'/config',
                  'simics-workspace/gold-checkpoints/' +
                  str(campaign_number)+'/'+checkpoint+'/config.bak')
        paths = simics_config.get_attr(config, 'sim', 'checkpoint_path')
        new_paths = []
        for path in paths:
            path_list = path.split('/')
            path_list = path_list[path_list.index('simics-workspace'):]
            path_list[-2] = str(campaign_number)
            new_paths.append('\"'+os.getcwd()+'/'+'/'.join(path_list))
        simics_config.set_attr(config, 'sim', 'checkpoint_path',
                               new_paths)
        simics_config.write_configuration(
            config, 'simics-workspace/gold-checkpoints/' +
            str(campaign_number)+'/'+checkpoint, False)


def update_all_checkpoint_dependencies():
    if os.path.exists('simics-workspace/gold-checkpoints'):
        print('updating gold checkpoint path dependencies...', end='')
        sys.stdout.flush()
        for campaign in os.listdir('simics-workspace/gold-checkpoints'):
            update_checkpoint_dependencies(campaign)
        print('done')


def merge_campaigns(merge_directory):
    backup_database()
    with sql(row_factory='row') as db, \
        sql(database=merge_directory+'/campaign-data/db.sqlite3',
            row_factory='dict') as db_new:
        db_new.cursor.execute('SELECT * FROM log_campaign')
        new_campaigns = db_new.cursor.fetchall()
        for new_campaign in new_campaigns:
            print('merging campaign: \"'+merge_directory+'/' +
                  new_campaign['command']+'\"')
            old_campaign_number = new_campaign['id']
            db.insert_dict('campaign', new_campaign)
            new_campaign['id'] = db.cursor.lastrowid
            if os.path.exists(merge_directory+'/campaign-data/' +
                              str(old_campaign_number)):
                print('\tcopying campaign data...', end='')
                shutil.copytree(merge_directory+'/campaign-data/' +
                                str(old_campaign_number),
                                'campaign-data/'+str(new_campaign['id']))
                print('done')
            if os.path.exists(merge_directory+'/simics-workspace/'
                              'gold-checkpoints/'+str(old_campaign_number)):
                print('\tcopying gold checkpoints...', end='')
                shutil.copytree(merge_directory+'/simics-workspace/'
                                'gold-checkpoints/'+str(old_campaign_number),
                                'simics-workspace/gold-checkpoints/' +
                                str(new_campaign['id']))
                print('done')
                print('\tupdating checkpoint dependency paths...', end='')
                sys.stdout.flush()
                update_checkpoint_dependencies(new_campaign['id'])
                print('done')
            print('\tcopying results...', end='')
            db_new.cursor.execute('SELECT * FROM log_result WHERE '
                                  'campaign_id=?', (old_campaign_number,))
            new_results = db_new.cursor.fetchall()
            for new_result in new_results:
                old_result_id = new_result['id']
                new_result['campaign_id'] = new_campaign['id']
                del new_result['id']
                db.insert_dict('result', new_result)
                new_result_id = sql.lastrowid
                for table in ['injection', 'simics_register_diff',
                              'simics_memory_diff']:
                    db_new.cursor.execute('SELECT * FROM log_'+table+' '
                                          'WHERE result_id=?', (old_result_id,))
                    new_result_items = db_new.cursor.fetchall()
                    for new_result_item in new_result_items:
                        new_result_item['result_id'] = new_result_id
                        del new_result_item['id']
                        db.insert_dict(table, new_result_item)
            print('done')


def launch_openocd(options):
    debugger = openocd(None, None, options.dut_serial_port, None, None, None,
                       None, None, None, None, standalone=True)
    print('Launched '+str(debugger))
    debugger.openocd.wait()


def launch_supervisor(options):
    supervisor(get_campaign_data(options.campaign_number), options).cmdloop()
