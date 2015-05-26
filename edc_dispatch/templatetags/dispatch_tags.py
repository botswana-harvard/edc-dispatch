from django import template
from ..models import DispatchItemRegister

register = template.Library()


@register.filter(name='is_dispatched')
def is_dispatched(item_identifier):
    """Returns dispatch status of the item based on the identifier."""
    locked = False
    if DispatchItemRegister.objects.filter(
            item_identifier=item_identifier,
            is_dispatched=True).exists():
        locked = True
    return locked


@register.filter(name='is_dispatched_item')
def is_dispatched_item(instance):
    """Returns dispatch status of the item based on the identifier."""
    return instance.is_dispatched_as_item()


@register.filter(name='dispatched_to')
def dispatched_to(item_identifier):
    """Returns the producer dispatch to based on the identifier."""
    if DispatchItemRegister.objects.filter(
            item_identifier=item_identifier,
            is_dispatched=True):
        dispatch_item = DispatchItemRegister.objects.get(
            item_identifier=item_identifier,
            is_dispatched=True)
    return dispatch_item.producer
