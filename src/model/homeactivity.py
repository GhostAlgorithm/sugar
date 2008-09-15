# Copyright (C) 2006-2007 Owen Williams.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA

import time
import logging
import os

import gobject
import dbus

from sugar.graphics.xocolor import XoColor
from sugar.presence import presenceservice
from sugar import profile
from sugar import wm

import config

_SERVICE_NAME = "org.laptop.Activity"
_SERVICE_PATH = "/org/laptop/Activity"
_SERVICE_INTERFACE = "org.laptop.Activity"

class HomeActivity(gobject.GObject):
    """Activity which appears in the "Home View" of the Sugar shell
    
    This class stores the Sugar Shell's metadata regarding a
    given activity/application in the system.  It interacts with
    the sugar.activity.* modules extensively in order to 
    accomplish its tasks.
    """

    __gtype_name__ = 'SugarHomeActivity'

    __gproperties__ = {
        'launching' : (bool, None, None, False,
                       gobject.PARAM_READWRITE),
    }

    def __init__(self, activity_info, activity_id, window=None):
        """Initialise the HomeActivity
        
        activity_info -- sugar.activity.registry.ActivityInfo instance,
            provides the information required to actually
            create the new instance.  This is, in effect,
            the "type" of activity being created.
        activity_id -- unique identifier for this instance
            of the activity type
        window -- Main WnckWindow of the activity 
        """
        gobject.GObject.__init__(self)

        self._window = None
        self._service = None
        self._activity_id = activity_id
        self._activity_info = activity_info
        self._launch_time = time.time()
        self._launching = False

        if window is not None:
            self.set_window(window)

        self._retrieve_service()

        if not self._service:
            bus = dbus.SessionBus()
            bus.add_signal_receiver(self._name_owner_changed_cb,
                                    signal_name="NameOwnerChanged",
                                    dbus_interface="org.freedesktop.DBus")

    def set_window(self, window):
        """Set the window for the activity

        We allow resetting the window for an activity so that we
        can replace the launcher once we get its real window.
        """
        if not window:
            raise ValueError("window must be valid")
        self._window = window

    def get_service(self):
        """Get the activity service
        
        Note that non-native Sugar applications will not have
        such a service, so the return value will be None in
        those cases.
        """

        return self._service

    def get_title(self):
        """Retrieve the application's root window's suggested title"""
        if self._window:
            return self._window.get_name()
        else:
            return ''

    def get_icon_path(self):
        """Retrieve the activity's icon (file) name"""
        if self.is_journal():
            return os.path.join(config.data_path, 'icons/activity-journal.svg')
        elif self._activity_info:
            return self._activity_info.icon
        else:
            return None
    
    def get_icon_color(self):
        """Retrieve the appropriate icon colour for this activity
        
        Uses activity_id to index into the PresenceService's 
        set of activity colours, if the PresenceService does not
        have an entry (implying that this is not a Sugar-shared application)
        uses the local user's profile.get_color() to determine the
        colour for the icon.
        """
        pservice = presenceservice.get_instance()

        # HACK to suppress warning in logs when activity isn't found
        # (if it's locally launched and not shared yet)
        activity = None
        for act in pservice.get_activities():
            if self._activity_id == act.props.id:
                activity = act
                break

        if activity != None:
            return XoColor(activity.props.color)
        else:
            return profile.get_color()
        
    def get_activity_id(self):
        """Retrieve the "activity_id" passed in to our constructor
        
        This is a "globally likely unique" identifier generated by
        sugar.util.unique_id
        """
        return self._activity_id

    def get_xid(self):
        """Retrieve the X-windows ID of our root window"""
        return self._window.get_xid()

    def get_window(self):
        """Retrieve the X-windows root window of this application
        
        This was stored by the set_window method, which was 
        called by HomeModel._add_activity, which was called 
        via a callback that looks for all 'window-opened'
        events.
        
        HomeModel currently uses a dbus service query on the
        activity to determine to which HomeActivity the newly
        launched window belongs.
        """
        return self._window

    def get_type(self):
        """Retrieve the activity bundle id for future reference"""
        if self._window is None:
            return None
        else:
            return wm.get_bundle_id(self._window)

    def is_journal(self):
        """Returns boolean if the activity is of type JournalActivity"""
        return self.get_type() == 'org.laptop.JournalActivity'

    def get_launch_time(self):
        """Return the time at which the activity was first launched
        
        Format is floating-point time.time() value 
        (seconds since the epoch)
        """
        return self._launch_time

    def get_pid(self):
        """Returns the activity's PID"""
        return self._window.get_pid()

    def equals(self, activity):
        if self._activity_id and activity.get_activity_id():
            return self._activity_id == activity.get_activity_id()
        if self._window.get_xid() and activity.get_xid():
            return self._window.get_xid() == activity.get_xid()
        return False

    def do_set_property(self, pspec, value):
        if pspec.name == 'launching':
            self._launching = value

    def do_get_property(self, pspec):
        if pspec.name == 'launching':
            return self._launching

    def _get_service_name(self):
        if self._activity_id:
            return _SERVICE_NAME + self._activity_id
        else:
            return None

    def _retrieve_service(self):
        if not self._activity_id:
            return

        try:
            bus = dbus.SessionBus()
            proxy = bus.get_object(self._get_service_name(),
                                   _SERVICE_PATH + "/" + self._activity_id)
            self._service = dbus.Interface(proxy, _SERVICE_INTERFACE)
        except dbus.DBusException:
            self._service = None

    def _name_owner_changed_cb(self, name, old, new):
        if name == self._get_service_name():
            self._retrieve_service()
            self.set_active(True)

    def set_active(self, state):
        """Propagate the current state to the activity object"""
        if self._service is not None:
            self._service.SetActive(state,
                                    reply_handler=self._set_active_success,
                                    error_handler=self._set_active_error)

    def _set_active_success(self):
        pass
    
    def _set_active_error(self, err):
        logging.error("set_active() failed: %s" % err)

