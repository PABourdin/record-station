# -*- coding: utf8 -*-
# rb-record-station v0.3 (Aug 2009)
#
# Copyright (C) 2008, 2010 Jannik Heller <scrawl@baseoftrash.de>
# Copyright (C)	2009 PhobosK <phobosk@kbfx.net>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA 02110-1301  USA.

import rhythmdb, rb
import gobject, gtk, gtk.glade, pango
import subprocess, os, time, threading, thread, ConfigParser, shutil, re
from gettext import *

ui_str = """
<ui>
  <popup name="IRadioViewPopup">
    <placeholder name="PlaylistViewPopupPluginPlaceholder">
      <menuitem name="RecordStationPopup" action="RecordStation"/>
      <menuitem name="PlannedRecordingPopup" action="PlannedRecording"/>
    </placeholder>
  </popup>

  <toolbar name="ToolBar">
    <placeholder name="PluginPlaceholder">
		<toolitem name="RecordStationButton" action="RecordStation"/>
		<toolitem name="RecordStationManager" action="RecordManager"/>
    </placeholder>
  </toolbar>
</ui>
"""

class RecordStation(rb.Plugin):
	def __init__(self):
		rb.Plugin.__init__(self)

	"""
	Get the user's music directory
	"""
	def get_xdg_music_dir(self):
		try:
			config_file = os.path.expanduser("~/.config/user-dirs.dirs")
			f = open(config_file, 'r')

			for line in f:
				if line.strip().startswith("XDG_MUSIC_DIR"):
					# get part after = , remove " and \n
					dir = line.split("=")[1].replace("\"", "").replace("\n", "")
					# replace $HOME with ~ (os.path.expanduser compability)
					dir = dir.replace("$HOME", os.path.expanduser("~"))
		except:
			# default dir if we dont find music dir
			dir = os.path.expanduser("~")
			
		return dir
	
	"""	
	Shows the dialog to add a planned recording
	ask_for_uri: If false, stream uri is gathered from currently selected radio entry, if true, the user is asked
	edit: If true, edit an existing entry ("name" disabled)
	"""
	def planned_recording(self, widget, ask_for_uri, edit):
		def cancel(widget, window):
			window.destroy()
			return None
		def add(widget, widgets, window, edit):
			name = widgets["name_entry"].get_text()
			# if not in edit mode, check if entry already exists
			if edit == False and name in self.plan.sections():
				dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
					_('Name is already in use!'))
				dialog.set_title(_('Error'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == gtk.RESPONSE_CLOSE:
					dialog.destroy()
				return None
			# check if name or stream is not empty			
			if name == "" or widgets["stream_entry"].get_text() == "":
				dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
					_('Please enter a valid name and stream!'))
				dialog.set_title(_('Error'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == gtk.RESPONSE_CLOSE:
					dialog.destroy()
				return None
			
			# convert time selection to UNIX timestamp
			day = widgets["day_entry"].get_value_as_int()
			month = widgets["month_entry"].get_value_as_int()
			year = widgets["year_entry"].get_value_as_int()
			hour = widgets["hour_entry"].get_value_as_int()
			print hour
			minute = widgets["minute_entry"].get_value_as_int()
			second = widgets["second_entry"].get_value_as_int()
			
			time_struct = (year, month, day, hour, minute, second, 0, 0, 0)
			
			if edit == False:
				self.plan.add_section(name)
			self.plan.set(name, "tm_year", year)
			self.plan.set(name, "tm_month", month)
			self.plan.set(name, "tm_day", day)
			self.plan.set(name, "tm_hour", hour)
			self.plan.set(name, "tm_minute", minute)
			self.plan.set(name, "tm_second", second)
			self.plan.set(name, "timestamp", int(time.mktime(time_struct)) + time.timezone )
			self.plan.set(name, "last_timestamp", int(time.mktime(time_struct)) + time.timezone - widgets["duration_entry"].get_value_as_int() )
			self.plan.set(name, "uri", widgets["stream_entry"].get_text() )
			self.plan.set(name, "folder", widgets["folderchooserbutton"].get_filename() )
			
			# set duration
			if widgets["duration_manual_radio"].get_active():
				self.plan.set(name, "duration", "manual_stop" )
			elif widgets["duration_timespan_radio"].get_active():
				# convert minutes -> seconds : * 60
				self.plan.set(name, "duration", widgets["duration_entry"].get_value_as_int() * 60 )
			elif widgets["duration_info_radio"].get_active():
				self.plan.set(name, "duration", "info_change" )
			# set repetition
			if widgets["repeat_cb"].get_active():
				if widgets["repeat_times_radio"].get_active():
					self.plan.set(name, "repetition_countdown", widgets["repeat_times_entry"].get_value_as_int())
				elif widgets["repeat_forever_radio"].get_active():
					self.plan.set(name, "repetition_countdown", True)
			else:
				self.plan.set(name, "repetition_countdown", False)
			# convert days -> seconds : * 86400
			self.plan.set(name, "repetition", widgets["repeat_entry"].get_value_as_int() * 86400)
			window.destroy()
			# preferences window may not be spawned
			try:
				self.update_plan_view()
			except:
				pass
			return
			
		def update_sensitive(widget, widgets):
			widgets["duration_entry"].set_sensitive( widgets["duration_timespan_radio"].get_active() )
			
			widgets["repeat_forever_radio"].set_sensitive( widgets["repeat_cb"].get_active() )
			widgets["repeat_entry"].set_sensitive( widgets["repeat_cb"].get_active() )
			widgets["repeat_times_radio"].set_sensitive( widgets["repeat_cb"].get_active() )
			widgets["repeat_times_entry"].set_sensitive( widgets["repeat_cb"].get_active() )
			widgets["times_label"].set_sensitive( widgets["repeat_cb"].get_active() )
	
		wTree = gtk.glade.XML(self.find_file("new_task.glade"))
		window = wTree.get_widget("window1")
		
		# init widgets
		widgets = {
			"name_entry" : wTree.get_widget("name_entry"),
			"stream_entry" : wTree.get_widget("stream_entry"),
			"folderchooserbutton" : wTree.get_widget("folderchooserbutton"),
			"day_entry" : wTree.get_widget("day_entry"),
			"month_entry" : wTree.get_widget("month_entry"),
			"year_entry" : wTree.get_widget("year_entry"),
			"hour_entry" : wTree.get_widget("hour_entry"),
			"minute_entry" : wTree.get_widget("minute_entry"),
			"second_entry" : wTree.get_widget("second_entry"),
			"duration_manual_radio" : wTree.get_widget("duration_manual_radio"),
			"duration_timespan_radio" : wTree.get_widget("duration_timespan_radio"),
			"duration_info_radio" : wTree.get_widget("duration_info_radio"),
			"duration_entry" : wTree.get_widget("duration_entry"),
			"repeat_cb" : wTree.get_widget("repeat_cb"),
			"repeat_entry" : wTree.get_widget("repeat_entry"),
			"repeat_combobox" : wTree.get_widget("repeat_combobox"),
			"repeat_times_radio" : wTree.get_widget("repeat_times_radio"),
			"repeat_times_entry" : wTree.get_widget("repeat_times_entry"),
			"repeat_forever_radio" : wTree.get_widget("repeat_forever_radio"),
			"cancel_button" : wTree.get_widget("cancel_button"),
			"ok_button" : wTree.get_widget("ok_button")
		}
		
		# load default time
		time_struct = time.localtime()
		widgets["year_entry"].set_value(time_struct[0])
		widgets["month_entry"].set_value(time_struct[1])
		widgets["day_entry"].set_value(time_struct[2])
		widgets["hour_entry"].set_value(time_struct[3])
		widgets["minute_entry"].set_value(time_struct[4])
		widgets["second_entry"].set_value(time_struct[5])
		
		widgets["repeat_forever_radio"].set_group(widgets["repeat_times_radio"])
		widgets["duration_timespan_radio"].set_group(widgets["duration_manual_radio"])
		widgets["duration_info_radio"].set_group(widgets["duration_manual_radio"])
		widgets["cancel_button"].connect( "clicked", cancel, window )
		widgets["ok_button"].connect( "clicked", add, widgets, window, edit )
		
		widgets["repeat_forever_radio"].connect("clicked", update_sensitive, widgets)
		widgets["repeat_cb"].connect("clicked", update_sensitive, widgets)
		widgets["duration_manual_radio"].connect("clicked", update_sensitive, widgets)
		widgets["duration_timespan_radio"].connect("clicked", update_sensitive, widgets)
		widgets["duration_info_radio"].connect("clicked", update_sensitive, widgets)
					
		# translate labels
		window.set_title( _('Planned recording') )
		wTree.get_widget("browser_views_label3").set_markup( _('<b>Basic settings</b>') )
		wTree.get_widget("label14").set_text( _('Stream') )
		wTree.get_widget("label15").set_text( _('Folder') )
		wTree.get_widget("browser_views_label").set_markup( _('<b>Time</b>') )
		wTree.get_widget("label2").set_text( _('Day') )
		wTree.get_widget("label3").set_text( _('Month') )
		wTree.get_widget("label4").set_text( _('Year') )
		wTree.get_widget("label5").set_text( _('Hour') )
		wTree.get_widget("label11").set_text( _('Minute') )
		wTree.get_widget("label12").set_text( _('Second') )
		wTree.get_widget("label4").set_text( _('Year') )
		wTree.get_widget("label17").set_text( _('Name') )
		wTree.get_widget("browser_views_label1").set_markup( _('<b>Duration</b>') )
		wTree.get_widget("browser_views_label2").set_markup( _('<b>Repetition</b>') )
		wTree.get_widget("label7").set_text( _('minutes') )
		widgets["times_label"] = wTree.get_widget("label10")
		widgets["times_label"].set_text( _('times') )
		wTree.get_widget("label16").set_text( _('day(s)') )
		
		widgets["folderchooserbutton"].set_title( _('Select folder') )
		widgets["duration_manual_radio"].set_label( _('Record until I stop') )
		widgets["duration_timespan_radio"].set_label( _('Record for') )
		widgets["duration_info_radio"].set_label( _('Record until stream info changes') )

		widgets["repeat_times_radio"].set_label( "" )
		widgets["repeat_forever_radio"].set_label( _('forever') )
		widgets["repeat_cb"].set_label( _('Event repeats every') )
		
		# load settings
		# stream uri
		if not ask_for_uri:
			# get stream uri from current selection
			source = self.shell.get_property("selected_source")
			entry = rb.Source.get_entry_view(source)
			selected = entry.get_selected_entries()
			if selected != []:
				uri = selected[0].get_playback_uri()
			else:
				uri = ""
				
			widgets["stream_entry"].set_text(uri)
		if edit:
			# if in edit mode, disable name entry
			widgets["name_entry"].set_text(edit)
			widgets["name_entry"].set_sensitive(False)
			# and load values
			widgets["stream_entry"].set_text( self.plan.get(edit, "uri") )
			widgets["folderchooserbutton"].set_filename( self.plan.get(edit, "folder") )
			
			# sync year/month/day with timestamp
			time_struct = time.localtime( int(self.plan.get(edit, "timestamp") ) )
			year = time_struct[0]
			month = time_struct[1]
			day = time_struct[2]
			hour = time_struct[3]
			minute = time_struct[4]
			second = time_struct[5]
			widgets["day_entry"].set_value( day )
			widgets["month_entry"].set_value( month )
			widgets["year_entry"].set_value( year )
			widgets["hour_entry"].set_value( hour )
			widgets["minute_entry"].set_value( minute )
			widgets["second_entry"].set_value( second )
			duration = self.plan.get(edit, "duration")
			if duration == "manual_stop":
				widgets["duration_manual_radio"].set_active(True)
			elif duration == "info_change":
				widgets["duration_info_radio"].set_active(True)
			else:
				widgets["duration_timespan_radio"].set_active(True)
				# convert seconds -> minutes : / 60
				widgets["duration_entry"].set_value( int(self.plan.get(edit, "duration")) / 60 )
			widgets["repeat_cb"].set_active( bool(self.plan.get(edit, "repetition_countdown")) )
			# convert seconds -> days : / 86400
			widgets["repeat_entry"].set_value( int(self.plan.get(edit, "repetition")) / 86400 )
			countdown = self.plan.get(edit, "repetition_countdown")
			if countdown == True:
				widgets["repeat_times_radio"].set_active(False)
				widgets["repeat_forever_radio"].set_active(True)
			else:
				widgets["repeat_times_radio"].set_active(True)
				widgets["repeat_forever_radio"].set_active(False)
			widgets["repeat_times_entry"].set_value( int(countdown))
			
			
		# folder
		widgets["folderchooserbutton"].set_filename( self.config.get("Ripping", "defaultdir") )
		
		# show
		update_sensitive(None, widgets)
		window.show_all()
	"""
	Activates the plugin on startup (basically just sets up the UI)
	"""
	def activate(self, shell):
		self.shell = shell
		
		# Load basic settings
		# Get the translation file
		install('rbrecord')
		# Store: stream name, dir, RecordProcess object, current song, recorded (num songs, size)
		self.record_db = gtk.TreeStore(gobject.TYPE_STRING, gobject.TYPE_STRING, object, gobject.TYPE_STRING, gobject.TYPE_STRING)

		# load configuration
		self.config = ConfigParser.RawConfigParser()
		self.config_file = os.path.expanduser("~") + "/.rbrec_conf"
		if os.path.isfile(self.config_file):
			self.config.read(self.config_file)
		else:
			# default options
			self.config.read("/usr/lib/rhythmbox/plugins/record-station/default.conf")
		# replace XDG_MUSIC_DIR with user's music directory
		if self.config.get("Ripping", "defaultdir") == "XDG_MUSIC_DIR":
			self.config.set("Ripping", "defaultdir", self.get_xdg_music_dir())
		# convert string to bool
		for section in self.config.sections():
			for item in self.config.items(section):
				if item[1] == "False":
					self.config.set(section, item[0], False)
				elif item[1] == "True":
					self.config.set(section, item[0], True)
		# load planned recordings
		self.plan = ConfigParser.RawConfigParser()
		self.plan_file = os.path.expanduser("~") + "/.rbrec_plan"
		if os.path.isfile(self.plan_file):
			self.plan.read(self.plan_file)
		# convert string to bool
		for section in self.plan.sections():
			for item in self.plan.items(section):
				if item[1] == "False":
					self.plan.set(section, item[0], False)
				elif item[1] == "True":
					self.plan.set(section, item[0], True)
		# is the record manager open?
		self.dialog_open = False
		# list with "incomplete" directories to be cleaned up on program quit
		self.cleanup = []
		
		# Set up UI
		# Set up actions
		self.action_popup = gtk.ToggleAction('RecordStation', _('Record'), _('Rip the selected internet radio station'), 'rb-record-station')
		self.action_plan = gtk.Action('PlannedRecording', _('Planned recording ...'), _('Create a planned recording for this radio station'), 'rb-record-station')
		self.action_manager = gtk.Action('RecordManager', _('Record Manager'), _('Show the record manager'), 'rb-record-station')
		self.activate_id_popup = self.action_popup.connect('activate', self.record_station)
		self.activate_id_plan = self.action_plan.connect('activate', self.planned_recording, False, False)
		self.activate_id_manager = self.action_manager.connect('activate', self.manage_dialog)

		self.action_group = gtk.ActionGroup('RecordStationPluginActions')
		self.action_group.add_action(self.action_popup)
		self.action_group.add_action(self.action_plan)
		self.action_group.add_action(self.action_manager)

		uim = self.shell.get_ui_manager ()
		uim.insert_action_group(self.action_group, 0)
		self.ui_id = uim.add_ui_from_string(ui_str)

		# Set up the popup menu
		popup_record=uim.get_widget('/ui/IRadioViewPopup/PlaylistViewPopupPluginPlaceholder/RecordStationPopup')
		popup_plan=uim.get_widget('/ui/IRadioViewPopup/PlaylistViewPopupPluginPlaceholder/PlannedRecordingPopup')
		image = gtk.Image()
		image.set_from_stock("gtk-media-record", gtk.ICON_SIZE_MENU)
		plan_image = gtk.Image()
		plan_image.set_from_stock("gtk-edit", gtk.ICON_SIZE_MENU)
		popup_plan.set_image(plan_image)
		#popup_record.set_image(image)

		# Set up the Record Toolbar Button
		self.btn_record=uim.get_widget('/ui/ToolBar/PluginPlaceholder/RecordStationButton')
		self.btn_record.set_stock_id("gtk-media-record")
		self.btn_record.set_label(_('Record'))

		# Set up the Record Manager Toolbar Button
		self.btn_manager=uim.get_widget('/ui/ToolBar/PluginPlaceholder/RecordStationManager')
		self.btn_manager.set_stock_id("gtk-connect")
		self.btn_manager.set_label(_('Record Manager'))

		uim.ensure_update()

		# Check if the source is Radio when starting and when source changes
		self.check_source(self, self.shell.get_property("selected_source"))
		self.source_list = self.shell.get_property("sourcelist")
		self.source_list_id  = self.source_list.connect ('selected', self.check_source)

		# reload stream metadata every 1/2s
		gobject.timeout_add(500, self.update_station_info)
		
		# check for planned recordings every 1/2 s
		gobject.timeout_add(500, self.update_plan)

		# wait 2 seconds before loading the radio source, rhythmbox might not yet be ready
		gobject.timeout_add(2000, self.get_radio_source)

	def get_radio_source(self):
		# watch for selection changes to update the toolbar
		try:
			# requires newer version of rhythmbox, so just try
			self.radio_source = self.shell.get_source_by_entry_type( self.shell.props.db.entry_type_get_by_name("iradio") )
		except:
			self.radio_source = self.shell.guess_source_for_uri("mms://x")
            	self.radio_source.get_entry_view().connect("selection-changed", self.update_toolbar)
            	self.record_button_automatically_set = False
		return False
            	
	"""
	Starts planned recordings, if available
	"""
	def update_plan(self):
		for item in self.plan.sections():
			timestamp = time.time()
			# event missed?
			if timestamp >= int(self.plan.get(item, "timestamp")) + 10:
				dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
					_('Planned recording missed: ') + str(item) )
				dialog.set_title(_('Warning'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == gtk.RESPONSE_CLOSE:
					dialog.destroy()
				# prepare for next repetition, or if there is none, dont drop section, but set timestamp to 99999999999
				if self.plan.get(item, "repetition_countdown") == False or int(self.plan.get(item, "repetition_countdown")) < 1:
					self.plan.set(item, "timestamp", 9999999999)
				else:
					self.plan.set(item, "timestamp", int(self.plan.get(item, "timestamp")) + int(self.plan.get(item, "repetition")) )
					if not type(True) == type(self.plan.get(item, "repetition_countdown")):
						self.plan.set(item, "repetition_countdown", int(self.plan.get(item, "repetition_countdown")) - 1 )
			# check for recordings to start
			if timestamp >= int(self.plan.get(item, "timestamp")):
				self.update_plan_view()
				print "starting"
				self.plan.set(item, "last_timestamp", int(self.plan.get(item, "timestamp")))
				rp = self.start_rip(None, self.plan.get(item, "uri"), True, self.plan.get(item, "folder"))
				rp.show_notifications = False
				rp.plan_item = item
				if self.plan.get(item, "duration") == "manual_stop":
					rp.record_until = True
				elif self.plan.get(item, "duration") == "info_change":
					rp.record_until = True
				else:
					rp.record_until = int( time.time() + int(self.plan.get(item, "duration")) )
				if self.config.get("Interface", "show_notifications") == True:
					os.system("notify-send --icon=gtk-media-record \"" + _('Automatic recording') + "\" \"" + item + "\"")
				# prepare for next repetition, or if there is none, dont drop section, but set timestamp to 99999999999
				if self.plan.get(item, "repetition_countdown") == False or int(self.plan.get(item, "repetition_countdown")) < 1:
					self.plan.set(item, "timestamp", 9999999999)
				else:
					self.plan.set(item, "timestamp", int(self.plan.get(item, "timestamp")) + int(self.plan.get(item, "repetition")) )
					if not type(True) == type(self.plan.get(item, "repetition_countdown")):
						self.plan.set(item, "repetition_countdown", int(self.plan.get(item, "repetition_countdown")) - 1 ) 
						
			# check for recordings that have finished
			if self.plan.get(item, "duration") == "info_change":
				
				# get RecordProcess
				i = 0
				for _item in self.record_db:
					if _item[2].uri == self.plan.get(item, "uri"):
						rp = _item[2]
						break
					i = i + 1
				try:
					if rp.song_num >= 2:
						# song info changed, recording finished
						self.update_plan_view()
						rp.stop(False)
						del self.record_db[i]
						if self.config.get("Interface", "show_notifications") == True:
							os.system("notify-send --icon=gtk-media-stop \"" + _('Automatic recording finished') + "\" \"" + item + "\"")
						if self.plan.get(item, "timestamp") == 9999999999:
							self.plan.remove_section(item)
				except:
					pass
			elif self.plan.get(item, "duration") == "manual_stop":
				pass
			else:
				# check if duration is over
				if time.time() >= int(self.plan.get(item, "duration")) + int(self.plan.get(item, "last_timestamp")):
					# get RecordProcess
					i = 0
					for _item in self.record_db:
						if _item[2].uri == self.plan.get(item, "uri"):
							rp = _item[2]
							break
						i = i + 1
					try:
						self.update_plan_view()
						rp.stop(False)
						del self.record_db[i]
						if self.config.get("Interface", "show_notifications") == True:
							os.system("notify-send --icon=gtk-media-stop \"" + _('Automatic recording finished') + "\" \"" + item + "\"")
						if self.plan.get(item, "timestamp") == 9999999999:
							self.plan.remove_section(item)
					except:
						pass
						
		# check if rhythmbox has been quit
		try:
			a = self.action_popup
		except:
			return False
		return True
	
	"""
	Deactivates the plugin
	"""
	def deactivate(self, shell):
		# Save configuration
		self.save_config()
		# Stop all rips on deactivation/quit
		self.stop_rip(self, True)
		if self.dialog_open == True:
			self.close_dialog(self.window)

		# Clean the UIs
		uim = self.shell.get_ui_manager()
		uim.remove_ui (self.ui_id)
		uim.remove_action_group (self.action_group)
		uim.ensure_update()

		# Stop watching for source changes
		self.source_list.disconnect (self.source_list_id)

		# Delete incomplete files
		if self.config.get("Ripping", "delete_incomplete") == True:
			for directory in self.cleanup:
				try:
					shutil.rmtree(directory)
				except:
					pass

		del self.action_group
		del self.action_popup
		del self.action_plan
		del self.action_manager
		del self.activate_id_popup
		del self.activate_id_plan
		del self.activate_id_manager
		del self.ui_id
		del self.btn_record
		del self.btn_manager
		del self.shell
		del self.source_list
		del self.source_list_id
		del self.record_button_automatically_set


	def update_plan_view(self):
		# preferences window may not be spawned
		try:
			self.plan_model.clear()
			for item in self.plan.sections():
				if not int(self.plan.get(item, "timestamp")) == 9999999999:
					self.plan_model.append( [item, time.ctime ( int(self.plan.get(item, "timestamp")) )    ] )
		except:
			pass
			
	"""
	Displays the configure dialog
	"""
	def create_configure_dialog(self, dialog=None):
		def ok_cb(widget, wTree):
			# save
			self.config.set("Ripping", "use_defaultdir", wTree.get_widget("default_folder_checkbox").get_active() )
			self.config.set("Ripping", "defaultdir", wTree.get_widget("folder_choose_button").get_current_folder() )
			self.config.set("Ripping", "create_subfolder", wTree.get_widget("subfolder_checkbox").get_active() )
			self.config.set("Ripping", "delete_incomplete", wTree.get_widget("delete_incomplete_checkbox").get_active() )
			self.config.set("Ripping", "single_file", wTree.get_widget("single_file_checkbox").get_active() )
			self.config.set("Interface", "show_notifications", wTree.get_widget("notify_checkbox").get_active() )
			self.config.set("Interface", "show_manager", wTree.get_widget("show_checkbox").get_active() )
			self.config.set("Columns", "stream", wTree.get_widget("stream_checkbox").get_active() )
			self.config.set("Columns", "current_title", wTree.get_widget("current_title_checkbox").get_active() )
			self.config.set("Columns", "folder", wTree.get_widget("folder_checkbox").get_active() )
			self.config.set("Columns", "recorded", wTree.get_widget("recorded_checkbox").get_active() )
			self.config.set("Compability", "use_mplayer", wTree.get_widget("use_mplayer_cb").get_active() )
			self.config.set("Compability", "regexp", wTree.get_widget("regexp_entry").get_text() )
			# manage dialog may not be spawned, so just try
			try:
				self.update_columns()
			except:
				pass
			window.destroy()
		def cancel_cb(widget, data=None):
			window.destroy()
		def add_cb(widget):
			name = self.planned_recording(None, True, False)
			self.update_plan_view()
		def remove_cb(widget, selection):
			rows = selection.get_selected_rows()
			count = selection.count_selected_rows()

			i = count
			while i > 0:
				id = rows[1][i-1]
				name = self.plan_model[id][0]
				self.plan.remove_section(name)
				i = i - 1
				
			self.update_plan_view()
		def edit_cb(widget):
			rows = selection.get_selected_rows()
			count = selection.count_selected_rows()

			i = len(rows[1])
			while i > 0:
				id = rows[1][i-1]
				name = self.plan_model[id][0]
				self.planned_recording(None, True, name)
				i = i - 1
		
		wTree = gtk.glade.XML(self.find_file("preferences.glade"))
		window = wTree.get_widget("preferences")
		window.set_title( _('Recording preferences') )
		
		# load widgets
		default_folder_checkbox = wTree.get_widget("default_folder_checkbox")
		folder_choose_button = wTree.get_widget("folder_choose_button")
		subfolder_checkbox = wTree.get_widget("subfolder_checkbox")
		delete_incomplete_checkbox = wTree.get_widget("delete_incomplete_checkbox")
		single_file_checkbox = wTree.get_widget("single_file_checkbox")
		notify_checkbox = wTree.get_widget("notify_checkbox")
		show_checkbox = wTree.get_widget("show_checkbox")
		stream_checkbox = wTree.get_widget("stream_checkbox")
		current_title_checkbox = wTree.get_widget("current_title_checkbox")
		folder_checkbox = wTree.get_widget("folder_checkbox")
		recorded_checkbox = wTree.get_widget("recorded_checkbox")
		ok_button = wTree.get_widget("ok_button")
		cancel_button = wTree.get_widget("cancel_button")
		add_button = wTree.get_widget("add_button")
		remove_button = wTree.get_widget("remove_button")
		edit_button = wTree.get_widget("edit_button")
		use_mplayer_checkbox = wTree.get_widget("use_mplayer_cb")
		regexp_entry = wTree.get_widget("regexp_entry")
		
		# load tree view
		view = wTree.get_widget("treeview1")
		selection = view.get_selection()
		self.plan_model = gtk.ListStore(gobject.TYPE_STRING, gobject.TYPE_STRING)
		view.set_model( self.plan_model )
		# load columns
		rend_name = gtk.CellRendererText()
		rend_name.set_property('editable', False)
		col_name = gtk.TreeViewColumn( _('Name'), rend_name, text=0)
		rend_time = gtk.CellRendererText()
		rend_time.set_property('editable', False)
		col_time = gtk.TreeViewColumn( _('Time'), rend_time, text=1)
		view.append_column(col_name)
		view.append_column(col_time)
		self.update_plan_view()
	
		# load config
		default_folder_checkbox.set_active( bool(self.config.get("Ripping", "use_defaultdir")) )
		folder_choose_button.set_current_folder( self.config.get("Ripping", "defaultdir") )
		folder_choose_button.set_title( _('Record Folder') )
		subfolder_checkbox.set_active( bool(self.config.get("Ripping", "create_subfolder")) )
		delete_incomplete_checkbox.set_active( bool(self.config.get("Ripping", "delete_incomplete")) )
		single_file_checkbox.set_active( bool(self.config.get("Ripping", "single_file") ) )
		notify_checkbox.set_active( bool(self.config.get("Interface", "show_notifications")) )
		show_checkbox.set_active( bool(self.config.get("Interface", "show_manager")) )
		stream_checkbox.set_active( bool(self.config.get("Columns", "stream")) )
		current_title_checkbox.set_active( bool(self.config.get("Columns", "current_title")) )
		folder_checkbox.set_active( bool(self.config.get("Columns", "folder")) )
		recorded_checkbox.set_active( bool(self.config.get("Columns", "recorded")) )
		ok_button.connect("clicked", ok_cb, wTree)
		cancel_button.connect("clicked", cancel_cb)
		add_button.connect("clicked", add_cb)
		remove_button.connect("clicked", remove_cb, selection)
		edit_button.connect("clicked", edit_cb)
		use_mplayer_checkbox.set_active( bool(self.config.get("Compability", "use_mplayer")) )
		regexp_entry.set_text( str(self.config.get("Compability", "regexp")) )
		
		# load translations
		wTree.get_widget("browser_views_label").set_markup( _('<b>Folder</b>') )
		wTree.get_widget("browser_views_label1").set_markup( _('<b>Recording</b>') )
		wTree.get_widget("browser_views_label2").set_markup( _('<b>Interface</b>') )
		wTree.get_widget("browser_views_label3").set_markup( _('<b>Columns</b>') )
		wTree.get_widget("nb_label_2").set_text( _('Planned recordings') )
		wTree.get_widget("compability_label").set_text( _('Compability') )
		wTree.get_widget("label1").set_markup( _('<i>To improve compability with some streams (including mms:// streams), you can use mplayer as a backend instead of streamripper. However, track information and file splitting is not supported then.</i>') )
		use_mplayer_checkbox.set_label( _('Use MPlayer for these Streams:') )
		default_folder_checkbox.set_label( _('Default folder') )
		subfolder_checkbox.set_label( _('Create a subfolder for each radio station') )
		delete_incomplete_checkbox.set_label( _('Automatically delete incomplete songs') )
		single_file_checkbox.set_label( _('Save to single file') )
		show_checkbox.set_label( _('Show the record manager when recording starts') )
		notify_checkbox.set_label( _('Display notifications') )
		stream_checkbox.set_label( _('Stream') )
		current_title_checkbox.set_label( _('Current title') )
		folder_checkbox.set_label( _('Folder') )
		recorded_checkbox.set_label( _('Recorded') )
		
		window.show_all()
		return window

	"""
	Save program configuration
	"""
	def save_config(self):
		f = open(self.config_file, 'w')
		self.config.write(f)
		f.close()
		
		f = open(self.plan_file, 'w')
		self.plan.write(f)
		f.close()
		
	"""
	Show toolbar buttons only in Radio source
	"""
	def check_source(self, widget, source):
		if source.get_property("name") == os.popen("gettext -d rhythmbox Radio").read():
			self.btn_record.show()
			self.btn_manager.show()
		else:
			self.btn_record.hide()
			self.btn_manager.hide()

	"""
	Create the dialog for folder selection
	"""
	def select_folder_dialog(self, action):
			return self.select_folder()
	def select_folder(self, uri=None):
		def close(self, widget):
			time.sleep(0.2)
			if self.checkbox.get_active():
				self.config.set("Ripping", "use_defaultdir", True)
			self.config.set("Ripping", "defaultdir", self.filechoose.get_filename() )
			self.filechoose.destroy()

		# Ask for folder to save the ripped content to
		wTree = gtk.glade.XML(self.find_file("dir_chooser.glade"))
		self.filechoose = wTree.get_widget("filechooserdialog1")
		self.filechoose.set_title( _('Record Folder') )
		if self.config.get("Ripping", "defaultdir") != "":
			self.filechoose.set_current_folder(self.config.get("Ripping", "defaultdir"))
		else:
			self.filechoose.set_current_folder(os.path.expanduser("~"))

		self.filechoose.show()
		self.checkbox = wTree.get_widget("checkbox")
		self.checkbox.set_label( _('Do not ask again') )
		cancel_button = wTree.get_widget("cancel_button")
		cancel_button.connect("clicked", lambda x:self.filechoose.destroy())
		ok_button = wTree.get_widget("ok_button")
		if uri!=None:
			ok_button.connect("clicked", self.start_rip, uri, False, "")
		else:
			ok_button.connect("clicked", self.save_config)

		ok_button.connect("clicked", lambda x:close(self, None))
		return self.filechoose

	"""
	Update the 'active' status of toolbar record button, according to the selection
	"""
	def update_toolbar(self, widget):
		source = self.shell.get_property("selected_source")
		entry = rb.Source.get_entry_view(source)
		selected = entry.get_selected_entries()
		if selected != []:
			self.btn_record.set_sensitive(True)
			# check if selected station is being recorded
			uri = selected[0].get_playback_uri()
			i = 0
			status = False
			for item in self.record_db:
				if item[2].uri == uri:
					status = True
					break
				i = i + 1
				
			if not(self.btn_record.get_active() == status):
				self.record_button_automatically_set = True
			self.btn_record.set_active(status)
		else:
			# if no stream is selected, set button to insensitive
			self.btn_record.set_sensitive(False)
			self.btn_record.set_active(False)

	"""
	Handle clicking of "Record" button and start ripping
	"""
	def record_station(self, action):
		if not self.record_button_automatically_set:
			if action.get_active():	
				source = self.shell.get_property("selected_source")
				entry = rb.Source.get_entry_view(source)
				selected = entry.get_selected_entries()
				if selected != []:
					uri = selected[0].get_playback_uri()
					if self.config.get("Ripping", "use_defaultdir") == False:
						self.select_folder(uri)
					else:
						self.start_rip(None, uri, True, self.config.get("Ripping", "defaultdir"))
			else:
				source = self.shell.get_property("selected_source")
				entry = rb.Source.get_entry_view(source)
				selected = entry.get_selected_entries()
				if selected != []:
					uri = selected[0].get_playback_uri()
					i = 0
					for item in self.record_db:
						if item[2].uri == uri:
							self.record_db[i][2].stop(self.config.get("Ripping", "delete_incomplete"))
							del self.record_db[i]
							return
						i = i + 1
		else:
			self.record_button_automatically_set = False
	
	"""
	Create record process
	returns: RecordProcess or None
	"""
	def start_rip(self, widget, uri, overrd, overrd_dir):
		# check if stream is already being recorded
		for entry in self.record_db:
			if entry[2].uri == uri:
				dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
					_('This stream is already being recorded!'))
				dialog.set_title(_('Error'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == gtk.RESPONSE_CLOSE:
					dialog.destroy()
				return None
		
		dir = self.config.get("Ripping", "defaultdir")
		if overrd:
			dir = overrd_dir
		# check if we need streamripper or mplayer
		if self.config.get("Compability", "use_mplayer") == True and re.match(self.config.get("Compability", "regexp"), str(uri)):
			# Create MPlayerProcess object
			recordprocess = MPlayerProcess(uri, str(dir))
			if self.config.get("Interface", "show_notifications") == True:
				os.system("notify-send --icon=gtk-info \"" + _('Recording in compability mode') + "\" \"" + _('Track information and file splitting will not be available') + "\"")
			recordprocess.start()
		else:
			# Create StreamripperProcess object
			recordprocess = StreamRipperProcess(uri, str(dir))
			if self.config.get("Ripping", "single_file") == True:
				recordprocess.single_file = True
			if self.config.get("Ripping", "create_subfolder") == True:
				recordprocess.create_subfolder = True
			else:
				# if the RecordProcess doesn't create a subfolder, RecordStation takes care of deleting incomplete files on program quit
				self.cleanup.append(str(dir) + "/incomplete")
			recordprocess.show_notifications = self.config.get("Interface", "show_notifications")
			recordprocess.start()

		self.add_row( [str(uri), str(dir), recordprocess, _('Unknown'), _('Nothing')] )
		
		if self.config.get("Interface", "show_manager") == True:
			self.manage_dialog(None)
			
		return recordprocess

	"""
	Handle the stop button in the manager (stop all selected processes) 
	"""
	def stop_rip(self, widget, all=False, clean=False):
		# Stop streamripper on exit (all=True and clean=False), on terminated subprocess (all=True and clean=True)
		# or when user chooses a process to stop (all=False and clean=False)
		if all:
			if self.dialog_open == False:
				self.manage_dialog(None)
				if clean == False:
					self.window.hide()

			self.tree_selection.select_all()

		rows = self.tree_selection.get_selected_rows()
		count = self.tree_selection.count_selected_rows()
		self.tree_selection.unselect_all()

		i = len(rows[1])
		while i > 0:
			id = rows[1][i-1]
			i = i - 1
			if clean:
				# Check for running subprocesses and leave them alone
				try:
					ret_code=self.record_db[id][2].process.poll()
					if ret_code == None:
						continue
				except OSError, e:
						pass

			# Terminate the subprocess Popen
			try:
				self.record_db[id][2].stop(self.config.get("Ripping", "delete_incomplete"))
				del self.record_db[id][2]
			except OSError, e:
				pass

			del self.record_db[id]
			
		# Refresh status of toolbar button
		try:
			self.update_toolbar(self.radio_source)
		except:
			pass

	"""
	Add an entry into the record db
	"""
	def add_row(self, values):
		self.record_db.append(None, values)

	"""
	Open the containing folder of the record material
	"""
	def open_folder(self, widget):
		rows = self.tree_selection.get_selected_rows()
		count = self.tree_selection.count_selected_rows()
		i = len(rows[1])
		# when nothing is selected, open the standard recording folder
		if i == 0:
			os.system("xdg-open \"" + self.config.get("Ripping", "defaultdir") + "\"")
		while i > 0:
			id = rows[1][i-1]
			folder = self.record_db[id][1]
			if not os.path.isdir(folder):
				# streamripper might have replaced some chars
				folder = folder.replace(".", "-")
			if not os.path.isdir(folder):
				# if we still cant find it, try the parent folder
				folder = get_parent_folder(folder)
					
			os.system("xdg-open \"" + folder + "\"")
			i = i - 1

	"""
	Only make the Stop / Open Folder / Play buttons active when there is a selection
	"""
	def update_button_active(self, widget, stop_button, folder_button, playback_button):
		if widget.count_selected_rows() < 1:
			status = False
			playback_button.set_sensitive(False)
		else:
			status = True
			playback_button.set_sensitive(status)
		
			# playback is not possible with multiple selection
			rows = self.tree_selection.get_selected_rows()
			count = self.tree_selection.count_selected_rows()
			if not count == 1:
				playback_button.set_sensitive(False)
			# playback is only possible with streamripper (not with mplayer)
			id = rows[1][0]
			try:
				self.record_db[id][2].relay_port
				playback_button.set_sensitive(True)
			except:
				playback_button.set_sensitive(False)
				
		stop_button.set_sensitive(status)
		folder_button.set_sensitive(True)

	"""
	Update radio station info (stream name, song info) for the record manager
	"""
	def update_station_info(self):
		self.record_db.foreach(self.update_station_info_foreach)
		# check if rhythmbox has been quit
		try:
			a = self.action_popup
		except:
			return False
		return True

	"""
	Records a radio station in compability mode
	"""	
	def record_compability_mode(self, uri):
		if self.config.get("Ripping", "use_defaultdir") == False:
			self.select_folder(uri)
	
		# check if stream is already being recorded
		for entry in self.record_db:
			if entry[2].uri == uri:
				dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
					_('This stream is already being recorded!'))
				dialog.set_title(_('Error'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == gtk.RESPONSE_CLOSE:
					dialog.destroy()
				return None
		
		dir = self.config.get("Ripping", "defaultdir")

		# Create MPlayerProcess object
		recordprocess = MPlayerProcess(uri, str(dir))
		if self.config.get("Interface", "show_notifications") == True:
			os.system("notify-send --icon=gtk-info \"" + _('Recording in compability mode') + "\" \"" + _('Track information and file splitting will not be available') + "\"")
		recordprocess.start()

		self.add_row( [str(uri), str(dir), recordprocess, _('Unknown'), _('Nothing')] )

		# obsolete because this method only gets invoked when normal recording failed - so the manager window should already be open if desired
		#if self.config.get("Interface", "show_manager") == True:
		#	self.manage_dialog(None)
		
	def update_station_info_foreach(self, model, path, iter, user_data=None):
		process = model[path][2]
		# check if process has quit
		if process.killed:
			del model[path]

			# ask the user if it should be recorded in compability mode
			if process.type == "streamripper":
				dialog = gtk.Dialog(_('Error'), None, 0, (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, _('Try compability mode'), gtk.RESPONSE_OK) )
				dialog.get_content_area().pack_start( gtk.Label( _('Could not record the stream! Do you want\n to record it in compability mode?\n\n') + process.uri ) )
				dialog.show_all()
				if dialog.run() == gtk.RESPONSE_OK:
					self.record_compability_mode(process.uri)
				dialog.destroy()
			else:
				dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
					_('Could not record the stream in compability mode! Please check that it is valid:\n\n') + process.uri)
				dialog.set_title(_('Error'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == gtk.RESPONSE_CLOSE:
					dialog.destroy()
			return True
		
		# get new data
		if process.song_num == 1:
			num_string = _('song')
		else:
			num_string = _('songs')
			
		size = int( float(process.song_size) + float(process.current_song_size) )
		recorded_info = str(process.song_num) + " " + num_string + " (" + str(convert_size(size)) + ")"
		stream_name = process.stream_name
		song_info = process.song_info
		directory = process.directory
		# only update if data has changed, to avoid unusable TreeView widget
		if not(recorded_info == self.record_db[path][4]):
			self.record_db[path][4] = recorded_info
		if not (stream_name == self.record_db[path][0]):
			self.record_db[path][0] = stream_name
		if not (song_info == self.record_db[path][3]):
			self.record_db[path][3] = song_info
		if not (directory == self.record_db[path][1]):
			self.record_db[path][1] = directory

	"""
	Close the record manager
	"""
	def close_dialog(self, widget, data=None):
		self.dialog_open = False		
		self.window.destroy()

	"""
	Playback streamripper relay
	"""
	def play_relay(self, widget):
		player = self.shell.get_player()
		player.stop()

		# get relay port from RecordProcess from TreeStore and stream name from TreeStore
		rows = self.tree_selection.get_selected_rows()
		count = self.tree_selection.count_selected_rows()
		i = len(rows[1])
		while i > 0:
			id = rows[1][i-1]
			process = self.record_db[id][2]
			name = self.record_db[id][0]
			i = i - 1
		relay_port = process.relay_port
		

		# register rhythmdb entry
		db_entry_type = self.shell.props.db.entry_register_type("RadioEntryType")
		db_entry_type.category = rhythmdb.ENTRY_STREAM
		db_entry = self.shell.props.db.entry_lookup_by_location("http://localhost:" + str(relay_port))
		if db_entry == None:
			db_entry = self.shell.props.db.entry_new(db_entry_type, "http://localhost:" + str(relay_port))
		# set entry name
		self.shell.props.db.set(db_entry, rhythmdb.PROP_TITLE, name) 
		
		# play
		player.play()
		player.play_entry(db_entry)
		
	"""
	Update show/hide of TreeView columnsin manager
	"""
	def update_columns(self):
		# first remove all existing columns
		if self.col_uri in self.view.get_columns():
			self.view.remove_column(self.col_uri)
		if self.col_song in self.view.get_columns():
			self.view.remove_column(self.col_song)
		if self.col_dir in self.view.get_columns():
			self.view.remove_column(self.col_dir)
		if self.col_recorded in self.view.get_columns():
			self.view.remove_column(self.col_recorded)
		# then add the ones we need
		if self.config.get("Columns", "stream"):
			self.view.append_column(self.col_uri)
		if self.config.get("Columns", "current_title"):
			self.view.append_column(self.col_song)
		if self.config.get("Columns", "folder"):
			self.view.append_column(self.col_dir)
		if self.config.get("Columns", "recorded"):
			self.view.append_column(self.col_recorded)
		
	"""
	Start the record manager
	"""
	def manage_dialog(self, widget=None):
		if self.dialog_open == False:
			self.dialog_open = True
			# Create the Manager window
			wTree = gtk.glade.XML(self.find_file("manage.glade"))
			self.window = wTree.get_widget("window1")
			self.window.set_position(gtk.WIN_POS_CENTER)
			self.window.set_title( _('Manage recordings') )
			self.window.show()
			self.window.connect("delete_event", self.close_dialog)

			# Setup the tree view
			self.view = wTree.get_widget("treeview")
			self.view.set_model(self.record_db)

			# initialize toolbar
			toolbar = wTree.get_widget("toolbar1")
			stop_button = gtk.ToolButton(gtk.STOCK_STOP)
			stop_button.set_label (_('Stop recording'))
			stop_button.set_tooltip_text (_('Stop recording'))
			stop_button.connect("clicked", self.stop_rip)
			toolbar.insert(stop_button, -1)
			
			folder_button = gtk.ToolButton(gtk.STOCK_OPEN)
			folder_button.set_label(_('Open folder'))
			folder_button.set_tooltip_text (_('Open folder'))
			folder_button.connect("clicked", self.open_folder)
			toolbar.insert(folder_button, -1)
			
			playback_button = gtk.ToolButton(gtk.STOCK_MEDIA_PLAY)
			playback_button.connect("clicked", self.play_relay)
			playback_button.set_tooltip_text (_('Play'))
			toolbar.insert(playback_button, -1)

			self.tree_selection = self.view.get_selection()
			self.tree_selection.set_mode(gtk.SELECTION_MULTIPLE)
			# change button "active" status when selection changes
			self.tree_selection.connect("changed", self.update_button_active, stop_button, folder_button, playback_button)
			self.update_button_active(self.tree_selection, stop_button, folder_button, playback_button)

			# initialize buttons
			preferences_button = wTree.get_widget("preferences_button")
			preferences_button.connect("clicked", self.create_configure_dialog)
			close_button = wTree.get_widget("close_button")
			close_button.connect("clicked", self.close_dialog)

			# initialize treeview
			# Use pango to render text so it is not oversized
			rend_uri = gtk.CellRendererText()
			rend_uri.set_property("editable", False)
			rend_uri.set_property("ellipsize",pango.ELLIPSIZE_END)
			rend_dir = gtk.CellRendererText()
			rend_dir.set_property("editable", False)
			rend_dir.set_property("ellipsize",pango.ELLIPSIZE_END)
			rend_song = gtk.CellRendererText()
			rend_song.set_property("editable", False)
			rend_song.set_property("ellipsize",pango.ELLIPSIZE_END)
			rend_recorded = gtk.CellRendererText()
			rend_recorded.set_property("editable", False)
			rend_recorded.set_property("ellipsize",pango.ELLIPSIZE_END)

			self.col_uri = gtk.TreeViewColumn( _('Stream'), rend_uri, text=0)
			self.col_uri.set_resizable(True)
			self.col_uri.set_expand(True)
			self.col_dir = gtk.TreeViewColumn( _('Directory'), rend_dir, text=1)
			self.col_dir.set_resizable(True)
			self.col_dir.set_expand(True)
			self.col_song = gtk.TreeViewColumn( _('Current title'), rend_dir, text=3)
			self.col_song.set_resizable(True)
			self.col_song.set_expand(True)
			self.col_recorded = gtk.TreeViewColumn( _('Recorded'), rend_dir, text=4)
			self.col_recorded.set_resizable(True)
			self.col_recorded.set_expand(True)

			# update show/hide of TreeView columns
			self.update_columns()
			self.window.show_all()
		else:
			self.window.present()

		# Delete obsolete rip processes
		self.stop_rip(self, True, True)

class MPlayerProcess(threading.Thread):
	def __init__(self, uri, basedirectory):
		threading.Thread.__init__(self)
		self.type = "mplayer"
		self.uri = uri
		self.stream_name = self.uri
		self.song_info = _('Unknown')
		self.song_num = 1 # number of ripped songs
		self.song_size = 0 # file size of all ripped songs (int, in kb)
		self.current_song_size = 0
		self.directory = basedirectory
		self.killed = False
		self.record_until = True # False: record until stream info changes, True: record until user stops, int: Record until timestamp
		self.plan_item = ""
		
	"""
	Open the process
	"""
	def start(self):
		# choose a file name
		basename = self.stream_name.replace("/", ".")
		i = 1
		found = False
		while found == False:
			if os.path.isfile(basename + " " + str(i)):
				i = i + 1
			else:
				found = True
		self.filename = basename + " " + str(i)
		
		options = []
		options.append("mplayer")
		options.append("-dumpstream")
		options.append(self.uri)
		options.append("-dumpfile")
		options.append(self.directory + "/" + self.filename)
		
		try:
			self.process = subprocess.Popen(options, 0, None, subprocess.PIPE, subprocess.PIPE, subprocess.PIPE)
		except OSError, e:
			print _('MPlayer binary not found! ERROR: %s') % e
			dialog = gtk.MessageDialog(None, gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, gtk.MESSAGE_ERROR, gtk.BUTTONS_CLOSE,
				_('MPlayer not found!\nPlease install the mplayer package from your distribution or install it manually from: http://www.mplayerhq.hu'))
			dialog.set_title(_('Missing binary file'))
			dialog.set_property("skip-taskbar-hint", False)
			if dialog.run() == gtk.RESPONSE_CLOSE:
				dialog.destroy()

			self.killed = True
			return False
			
		thread.start_new_thread(self.reload_info, ())
	"""
	Refresh file size
	"""
	def reload_info(self):
		while self.process.poll()==None:
			try:
				self.song_size = os.path.getsize(self.directory + "/" + self.filename) / 1000
			except OSError, e:
				self.song_size = 0
			line = ""
			while True:
				try:
					char = pout.read(1)
				except:
					break

				if char == None or char == "":
					break

				if char == "\n":
					break
				if char == "\r":
					break
				line = line+char
			if not line == "":
				print line
		# process has terminated, reload_info no longer needed
		self.killed = True
		return False
		
	"""
	Terminate the process
	"""
	def stop(self, clean=False):
		try:
			self.process.terminate()
		except:
			pass
		
"""
This class represents a single recording
"""
class StreamRipperProcess(threading.Thread):
	def __init__(self, uri, basedirectory):
		threading.Thread.__init__(self)
		self.type = "streamripper"
		self.relay_port = None # streamripper relay port
		self.stream_name = _('Unknown')
		self.uri = uri
		self.song_info = _('Unknown')
		self.song_num = 0 # number of ripped songs
		self.song_size = 0 # file size of all ripped songs (int, in kb)
		self.current_song_size = 0 # file size of currently ripping song (int, in kb)
		self.basedirectory = basedirectory
		self.directory = self.basedirectory
		self.create_subfolder = False
		self.killed = False
		self.show_notifications = False
		self.record_until = True # False: record until stream info changes, True: record until user stops, int: Record until timestamp
		self.plan_item = ""
		self.single_file = False

	"""
	Open the process
	"""
	def start(self):
		options = []
		options.append("streamripper")
		options.append(self.uri)
		options.append("-t")
		if self.create_subfolder == False:
			options.append("-s")
		if self.single_file == True:
			options.append("-a")
			options.append("-A")
		options.append("-r")
		options.append("-d")
		options.append(self.basedirectory)
		
		try:
			self.process = subprocess.Popen(options, 0, None, subprocess.PIPE, subprocess.PIPE, subprocess.PIPE)
		except OSError, e:
			print _('Streamripper binary not found! ERROR: %s') % e
			dialog = gtk.MessageDialog(None,
		     gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
					 gtk.MESSAGE_ERROR,
		     gtk.BUTTONS_CLOSE,
					 _('Streamripper not found!\nPlease install the streamripper package from your distribution or install it manually from: http://streamripper.sourceforge.net'))
			dialog.set_title(_('Missing binary file'))
			dialog.set_property("skip-taskbar-hint", False)
			if dialog.run() == gtk.RESPONSE_CLOSE:
				dialog.destroy()

			self.killed = True
			return False
		thread.start_new_thread(self.reload_info, ())

	"""
	Reload song info etc.
	"""
	def reload_info(self):
		pout = self.process.stdout
		while self.process.poll()==None:
			line = ""
			
			while True:
				try:
					char = pout.read(1)
				except:
					break

				if char == None or char == "":
					break

				if char == "\n":
					break
				if char == "\r":
					break
				line = line+char

			if line.startswith("relay port"):
				self.relay_port = line.split(":")[1].strip()
			if line.startswith("stream"):
				self.stream_name = line.split(":")[1].strip()
			if line.startswith("[ripping") or line.startswith("[skipping"):
				if not(self.song_info == line[17:-10]):
					# when song info changes
					if self.show_notifications:
						os.system("notify-send --icon=gtk-media-record \"" + line[17:-10] + "\" \"" + self.stream_name + "\"")
					self.song_num = self.song_num + 1
					self.song_size = float(self.song_size) + float(self.current_song_size)
				self.current_song_size = float(parse_size( line[len(line)-8:len(line)-1].strip() ))
				self.song_info = line[17:-10]
				

		# process has terminated, reload_info no longer needed
		self.killed = True
		return False

	"""
	Terminate process & clean incomplete files if needed
	"""
	def stop(self, clean=False):
		try:
			self.process.terminate()
		except:
			pass
		# if an own subfolder is created, RecordProcess can delete incomplete files, else this must be done on program quit
		if clean == True and self.create_subfolder == True:
			try:
				shutil.rmtree(self.directory + "/incomplete")
			except:
				pass
"""
Returns the parent folder
"""
def get_parent_folder(folder):
	# remove closing / if it is there
	if folder[len(folder)-1] == "/":
		folder = folder[0:len(folder)-2]

	split = folder.split("/")
	# delete the last folder in the tree, so we get the parent folder
	del split[len(split)-1]
	del split[0]
	folder = ""
	for element in split:
		folder += "/" + element
	return folder

"""
Parse size info e.g. 742kb, 1,2M to int in kb
returns: int size (in kb)
"""
def parse_size(str):
	format = ""
	if str.strip() == "0b":
		return 0
	if "," in str:
		intsize = int(str.split(",")[0])
		floatsize = float( str[0:len(str)-2].replace(",", ".") )
		format = str[len(str)-1:len(str)]
		if format == "kb":
			return intsize
		if format == "M":
			return floatsize*1000
	format_kb = str[len(str)-2:len(str)]
	format_mb = str[len(str)-1:len(str)]
	if format_kb == "kb":
		format = "kb"
	if format_mb == "M":
		format = "mb"
	num = float( str[0:len(str)-2] )
	if format == "kb":
		return num
	if format == "mb":
		return num*1000
	return num
"""
convert size (int) in kb to string (KB/MB/GB)
returns: string
"""
def convert_size(size):
	if size >= 1000000:
		return str(size / 1000000) + " GB"
	if size >= 1000:
		return str(size / 1000) + " MB"
	return str(size) + " KB"
