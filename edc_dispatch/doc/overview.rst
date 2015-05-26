Overview
========

Dispatch data from the main server to mobile devices or netbooks. Data is "dispatched" to the device 
and edited on the device. When editing is complete, data is returned to the server. While "dispatched" 
data on the server may not be altered.

Devices are "prepared" for use with :mod:`bhp_dispatch`. Once "prepared", data may be dispatched
to the device, edited and returned.

Data is selected for dispatch by the user. Within a project, the identifier of a single model is used
to select data for dispatch and track the "dispatch" status of data. For example, the subject identifier 
from RegisteredSubject. 

In the Mochudi Project the Household Identifier from the Household model is used instead of RegisteredSubject. 
The Household model contains Household Members which may or may not be referenced in RegisteredSubject. 
Once a Household is selected for dispatch, the household and all the data of the members in the household 
are dispatched to the device. Until the Household is returned, no data contained within the household 
may be edited on the server.

:mod:`bhp_dispatch` uses :mod:`bhp_sync` to return data.