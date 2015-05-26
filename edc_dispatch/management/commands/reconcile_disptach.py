from optparse import make_option

from django.db.models import get_model
from django.core.management.base import BaseCommand, CommandError

from edc.device.sync.models import Producer
from edc.device.sync.utils import load_producer_db_settings


class Command(BaseCommand):
    """ Sends an email to a list of recipients about the status of uploading transaction files
    """
    args = ('--producer')

    help = 'Reconcile dispatch item registers with the producer.'

    option_list = BaseCommand.option_list + (
        make_option(
            '--producer',
            dest='producer',
            action='store_true',
            default=False,
            help=('Enter producer name')),
        )

    def handle(self, *args, **options):
        if len(args) == 0 or len(args) == 1:
            pass
        else:
            raise CommandError('Command expecting One or Zero arguments. One being --producer <producer_name>')
        if options['producer']:
            self.reconcile(producer=args[0])
        else:
            self.reconcile()

    def reconcile(self, producer=None):
        load_producer_db_settings()
        DispatchItemRegister = get_model('dispatch', 'DispatchItemRegister')
        producer_list = []
        if producer and not Producer.objects.filter(name=producer, is_active=True):
            print 'Producer \'{}\' is not active'.format(producer)
        elif producer and Producer.objects.filter(name=producer, is_active=True):
            producer_list = [producer]
        else:
            producer_list = [pr.name for pr in Producer.objects.filter(is_active=True)]
        dispatched_items = DispatchItemRegister.objects.filter(producer__name__in=producer_list)
        print '============================='
        for item in dispatched_items:
            app = item.item_app_label
            model = item.item_model_name
            Model = get_model(app, model)
            try:
                #name = item.producer.name.split('-')[0]
                Model.objects.using(item.producer.name).get(id=item.item_pk)
                print 'Found instance of \'{}\' in \'{}\' with pk={}'.format(model, item.producer.name, item.item_pk)
            except Model.DoesNotExist:
                print 'MISSING instance of \'{}\' in \'{}\' with pk={}'.format(model, item.producer.name, item.item_pk)
        print "DONE"
        print '============================='
