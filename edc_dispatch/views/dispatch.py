from django.contrib import messages
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import get_model, get_models

from edc.device.dispatch.exceptions import (AlreadyDispatchedContainer, AlreadyDispatchedItem,
                                            AlreadyDispatched)
from edc.device.sync.exceptions import PendingTransactionError
from edc.device.sync.models import Producer

from ..classes import DispatchController
from ..exceptions import DispatchAttributeError
from ..forms import DispatchForm
from ..models import DispatchItemRegister


@login_required
def dispatch(request, dispatch_controller_cls, dispatch_form_cls=None, **kwargs):
    """Receives a list of user container identifiers and user selects
    the producer to dispatch to.

    Args:
        dispatch_controller_cls: a subclass of :class:`DispatchController`
            coming from a user app, e.g. MochudiDispatchController.
    """
    if not issubclass(dispatch_controller_cls, DispatchController):
        raise AttributeError('Parameter \'dispatch_controller_cls\' must be a '
                             'subclass of DispatchController.')
    if not dispatch_form_cls:
        dispatch_form_cls = DispatchForm
    msg = None
    producer = request.GET.get('producer', None)
    app_name = kwargs.get('app_name', None)
    if not app_name:
        raise AttributeError('keyword argument app_name cannot be None. This is in '
                             'edc/device/dispatch/views/dispatch.py')
    has_outgoing_transactions = False
    user_container = ''
    dispatch_url = ''
    user_container_model_name = ''
    user_container_admin_url = ''
    ct = None
    queryset = None
    notebook_plot_list_status = None
    if request.method == 'POST':
        """
        POST method is used for dispatching plots either for notebook_plot_list or the original way.
        """
        form = dispatch_form_cls(request.POST)
        if form.is_valid():
            dispatch_url = ''
            producer = form.cleaned_data.get('producer')
            ct = request.POST.get('ct')
            user_container_ct = ct
            survey = form.cleaned_data.get('survey', None)
            items = request.POST.get('items')
            pks = items.split(',')
            user_container_model_cls = ContentType.objects.get(pk=user_container_ct).model_class()
            user_container_model_name = user_container_model_cls._meta.verbose_name
            # TODO:  url should be reversed
            user_container_admin_url = '/admin/{0}/{1}/'.format(
                user_container_model_cls._meta.app_label, user_container_model_cls._meta.object_name.lower())
            user_containers = user_container_model_cls.objects.filter(pk__in=pks)
            if producer:
                try:
                    plot_list_status = request.POST.get('plot_list')
                    # if plot_list_status is not_allocated, dispatch uses the original logic otherwise dispatches to notebook_plot_list.
                    if plot_list_status == 'not_allocated':
                        if not producer.settings_key:
                            raise DispatchAttributeError('Producer attribute settings_key may not be None.')
                        for user_container in user_containers:
                            dispatch_controller = dispatch_controller_cls(
                                'default', producer.settings_key, user_container, **kwargs)
                            msg = dispatch_controller.dispatch(survey=survey)
                            messages.add_message(request, messages.SUCCESS, msg)
                        if dispatch_controller:
                            dispatch_url = dispatch_controller.get_dispatch_url()
                    else:
                        user_container_ct = request.POST.get('ct1')
                        user_containers = user_container_model_cls.objects.filter(pk__in=pks)
                        user_container_model_cls = ContentType.objects.get(pk=user_container_ct).model_class()
                        notebook_book_plots = []
                        for plot in user_containers:
                            nt = user_container_model_cls(plot_identifier=plot.plot_identifier)
                            notebook_book_plots.append(nt)

                        if not producer.settings_key:
                            raise DispatchAttributeError('Producer attribute settings_key may not be None.')
                        for notebook_plot_list in notebook_book_plots:
                            kwargs.update({'skip_container': True})
                            dispatch_controller = dispatch_controller_cls(
                                'default', producer.settings_key, notebook_plot_list, **kwargs)
                            msg = dispatch_controller.dispatch(survey=survey, plot_list_status=plot_list_status, notebook_plot_list=notebook_plot_list)
                            notebook_plot_list_status = request.POST.get('plot_list')  # set notebook_plot_list status from a dispatch form (dispatch.html)
                            #msg = 'Successfully dispatched {0} {1}'.format(user_container._meta.object_name, self.get_user_container_identifier())
                            messages.add_message(request, messages.SUCCESS, msg)
                        if dispatch_controller:
                            dispatch_url = dispatch_controller.get_dispatch_url()

                except PendingTransactionError as pending_transaction_error:
                    messages.add_message(request, messages.ERROR, str(pending_transaction_error))
                except AlreadyDispatchedContainer as already_dispatched_container:
                    messages.add_message(request, messages.ERROR, str(already_dispatched_container))
                except AlreadyDispatchedItem as already_dispatched_item:
                    messages.add_message(request, messages.ERROR, str(already_dispatched_item))
                except AlreadyDispatched as already_dispatched:
                    messages.add_message(request, messages.ERROR, str(already_dispatched))
    else:
        """
        For all dispatch actions selected from plots list view, they will use GET method.
        """
        ct = request.GET.get('ct')
        items = request.GET.get('items')
        notebook_plot_list_status = request.GET.get('notebook_plot_list')

        pks = None
        if items:
            pks = items.split(',')
        model_cls = ContentType.objects.get(pk=ct).model_class()
        queryset = model_cls.objects.filter(pk__in=pks)
        form = dispatch_form_cls()
    return render(request, 'dispatch.html', {
        'form': form,
        'ct': ct,
        'ct1': request.GET.get('ct1'),
        'items': items,
        'queryset': queryset or user_containers,
        'producer': producer,
        'producer_cls': Producer,
        'dispatchitemregister_cls': DispatchItemRegister,
        'has_outgoing_transactions': has_outgoing_transactions,
        'dispatch_url': dispatch_url,
        'user_container_model_name': user_container_model_name,
        'user_container_admin_url': user_container_admin_url,
        # 'title': 'Dispatch to Producer',
        'app_name': app_name,
        'notebook_plot_list': notebook_plot_list_status
        })
