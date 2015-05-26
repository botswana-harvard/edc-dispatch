Preparation
===========

For a device to be ready to receive "dispatched" data, run :func:`prepare_netbook`. 
Before running :func:`prepare_netbook`, setup the device database and confirm the settings.DATABASE options
are correct.

.. note:: These steps only need to be run once.

Setup database
+++++++++++++++
The database on the device is set up in the same way as any django project except the superuser 
account should NOT be created. The superuser account information will be dispatched from the server 
when :func:`prepare_netbook` is run.

1. Using ``mysql`` on the device, create a new database.

    If DB does not exist on device::
    
        mysql -u root -p -Bse 'create database bhp041_survey;'
        
    If DB already exists on device `(be careful!)`::
    
        mysql -u root -p -Bse 'drop database bhp041_survey; create database bhp041_survey;'
   
2. Comment out 'south' in INSTALLED_APPS.

3. Run django's ``syncdb``::

    python manage.py syncdb --noinput
    
  .. note:: Use parameter '--noinput' so syncdb does not prompt to create a superuser account.
    
4. Uncomment 'south' in INSTALLED_APPS.

5. Re-run ``syncdb`` to create the south migration history table::
    
    python manage.py syncdb

6. Fake migrations::

    python manage.py migrate --fake
    
The database on the device is now ready for :func:`prepare_netbook`.

Confirm options in settings.DATABASE
++++++++++++++++++++++++++++++++++++++

Before running :func:`prepare_netbook`, confirm the settings.DATABASE options are correct.

On the device
    * server options name: `server` (confirm the IP Address)
    * device options name: `default`

On the server:
    * server options name: `default`
    * device options name: anything but usually <hostname> or <hostname-DB> (e.g. `mpp83` or `mpp83-bhp041_survey`)
    
.. note:: In all cases the server is the `source`. :mod:`bhp_dispatch` does not move data from device to server.
          To move data from device to server see :mod:`bhp_sync`.

Run prepare_device Management Command
++++++++++++++++++++++++++++++++++++++

:func:`prepare_device` may be run from the device or the server. The options of the DATABASE attribute are those defined
in the :file:`settings.py` of the project folder from where the command is run::

    python manage.py prepare_device <source> <destination>
    
where `source` and `destination` must be valid option names in the DATABASE attribute of settings.py.    

If on the device::
 
    python manage.py prepare_device server default
    
If on the server::

    python manage.py prepare_device default mpp83

where `mpp83` is the name of settings.DATABASE options for the device.

 

.. note:: The management command might not be called `prepare_device` depending on the implementation.
          The command uses an instance of class :class:`PrepareDevice`. This may be wrapped in a 
          management command of a different name, for example, `prepare_netbook`. Type ``manage.py --help``
          to see a full list of management commands.