from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render_to_response
from django.template import RequestContext
from django.db.models import get_model
from ..models import DispatchContainerRegister
from ..classes import ReturnController


@login_required
def return_items(request, **kwargs):
    """ Return items from the producer to the source."""
    msg = None
    items = request.GET.get('items').split(',')
    user_container_list = []
    dispatch_container_register = DispatchContainerRegister.objects.get(id=items[0])
    previous = dispatch_container_register
    current = None
    defaults = {}
    container_model = get_model(dispatch_container_register.container_app_label, dispatch_container_register.container_model_name)
    if not container_model:
         raise TypeError('Dispatch Container model \'{0}\' does not exist. Got from DispatchContainerRegister of id \'{1}\'.'.format(dispatch_container_register.container_app_label+','+dispatch_container_register.container_model_name, dispatch_container_register.id))
    for item in items:
        current = DispatchContainerRegister.objects.get(id=item)
        if current.producer != previous.producer:
            raise TypeError('All items to be returned must be in the same producer. Got \'{0}\' and \'{1}\'.'.format(current, previous))
        defaults[current.container_identifier_attrname] = current.container_identifier
        user_container_list.append(container_model.objects.get(**defaults))
        previous = current
        defaults = {}
    producer = current.producer
    msg = ReturnController('default', producer.name).return_selected_items(user_container_list)
    messages.add_message(request, messages.INFO, msg)
    return render_to_response(
        'return_items.html', {'producer': producer, },
        context_instance=RequestContext(request)
        )
