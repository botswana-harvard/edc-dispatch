Dispatching
============

Preventing data edits on dispatched items
+++++++++++++++++++++++++++++++++++++++++

To prevent data edits on Subject data, add a model method to test that dispatch status and
refer to this method in the :file:`forms.py` :func:`clean` method.

This is in place by default for appointments and visit models. 

Add to the registered subject model::

    @property
    def is_dispatched(self):
        """Returns lock status as a boolean needed when using this model with bhp_dispatch."""
        locked, producer = self.is_dispatched_to_producer()
        return locked

    def is_dispatched_to_producer(self):
        """Returns lock status as a boolean needed when using this model with bhp_dispatch."""
        locked = False
        producer = None
        if DispatchItem.objects.filter(
                subject_identifiers__icontains=self.registered_subject.subject_identifier,
                is_dispatched=True).exists():
            dispatch_item = DispatchItem.objects.get(
                subject_identifiers__icontains=self.registered_subject.subject_identifier,
                is_dispatched=True)
            producer = dispatch_item.producer
            locked = True
        return locked, producer


Add to the :file:`forms.py` :func:`clean` method::

    def clean(self):
        if cleaned_data.get('registered_subject', None):
            registered_subject = cleaned_data.get('registered_subject')
            dispatched, producer_name = registered_subject.is_dispatched_to_producer()
            if dispatched:
                raise forms.ValidationError("Data for {0} is currently dispatched to netbook {1}. "
                                 "This form may not be modified.".format(registered_subject.subject_identifier,
                                                                          producer_name))