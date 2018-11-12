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

# Required packages:
# apt-get install python-gtk2-dev python-gi-dev python-gobject-dev python-gobject-2-dev

import sys
from gi.repository import RB, GObject, Peas, Gtk, Gio, GLib, Pango
import subprocess, os, time, threading, configparser, shutil, re
from gettext import *

import gettext
gettext.install('rhythmbox', RB.locale_dir())

class RecordStation(GObject.GObject, Peas.Activatable):
	__gtype_name__ = 'RecordStation'
	object = GObject.property(type=GObject.GObject)

	def __init__(self):
		GObject.Object.__init__(self)

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
	def planned_recording(self, action, widget, ask_for_uri, edit):
		shell = self.object
		def cancel(widget, window):
			window.destroy()
			return None
		def add(widget, widgets, window, edit):
			name = widgets["name_entry"].get_text()
			# if not in edit mode, check if entry already exists
			if edit == False and name in self.plan.sections():
				dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, _('Name is already in use!'))
				dialog.set_title(_('Error'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == Gtk.ResponseType.CLOSE:
					dialog.destroy()
				return None
			# check if name or stream is not empty
			if name == "" or widgets["stream_entry"].get_text() == "":
				dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, _('Please enter a valid name and stream!'))
				dialog.set_title(_('Error'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == Gtk.ResponseType.CLOSE:
					dialog.destroy()
				return None

			# convert time selection to UNIX timestamp
			day = widgets["day_entry"].get_value_as_int()
			month = widgets["month_entry"].get_value_as_int()
			year = widgets["year_entry"].get_value_as_int()
			hour = widgets["hour_entry"].get_value_as_int()
			minute = widgets["minute_entry"].get_value_as_int()
			second = widgets["second_entry"].get_value_as_int()

			time_struct = (year, month, day, hour, minute, second, 0, 0, -1)

			if edit == False:
				self.plan.add_section(name)
			self.plan.set(name, "tm_year", year)
			self.plan.set(name, "tm_month", month)
			self.plan.set(name, "tm_day", day)
			self.plan.set(name, "tm_hour", hour)
			self.plan.set(name, "tm_minute", minute)
			self.plan.set(name, "tm_second", second)
			self.plan.set(name, "timestamp", int(time.mktime(time_struct)) )
			self.plan.set(name, "last_timestamp", int(time.mktime(time_struct)) - widgets["duration_entry"].get_value_as_int() )
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

		gui = Gtk.Builder()
		gui.add_from_file("new_task.glade")
		window = gui.get_object("window1")

		# init widgets
		widgets = {
			"name_entry" : gui.get_object("name_entry"),
			"stream_entry" : gui.get_object("stream_entry"),
			"folderchooserbutton" : gui.get_object("folderchooserbutton"),
			"day_entry" : gui.get_object("day_entry"),
			"month_entry" : gui.get_object("month_entry"),
			"year_entry" : gui.get_object("year_entry"),
			"hour_entry" : gui.get_object("hour_entry"),
			"minute_entry" : gui.get_object("minute_entry"),
			"second_entry" : gui.get_object("second_entry"),
			"duration_manual_radio" : gui.get_object("duration_manual_radio"),
			"duration_timespan_radio" : gui.get_object("duration_timespan_radio"),
			"duration_info_radio" : gui.get_object("duration_info_radio"),
			"duration_entry" : gui.get_object("duration_entry"),
			"repeat_cb" : gui.get_object("repeat_cb"),
			"repeat_entry" : gui.get_object("repeat_entry"),
			"repeat_combobox" : gui.get_object("repeat_combobox"),
			"repeat_times_radio" : gui.get_object("repeat_times_radio"),
			"repeat_times_entry" : gui.get_object("repeat_times_entry"),
			"repeat_forever_radio" : gui.get_object("repeat_forever_radio"),
			"cancel_button" : gui.get_object("cancel_button"),
			"ok_button" : gui.get_object("ok_button")
		}

		# load default time
		time_struct = time.localtime()
		widgets["year_entry"].set_value(time_struct[0])
		widgets["month_entry"].set_value(time_struct[1])
		widgets["day_entry"].set_value(time_struct[2])
		widgets["hour_entry"].set_value(time_struct[3])
		widgets["minute_entry"].set_value(time_struct[4])
		widgets["second_entry"].set_value(time_struct[5])

		widgets["repeat_forever_radio"].join_group(widgets["repeat_times_radio"])
		widgets["duration_timespan_radio"].join_group(widgets["duration_manual_radio"])
		widgets["duration_info_radio"].join_group(widgets["duration_manual_radio"])
		widgets["cancel_button"].connect( "clicked", cancel, window )
		widgets["ok_button"].connect( "clicked", add, widgets, window, edit )

		widgets["repeat_forever_radio"].connect("clicked", update_sensitive, widgets)
		widgets["repeat_cb"].connect("clicked", update_sensitive, widgets)
		widgets["duration_manual_radio"].connect("clicked", update_sensitive, widgets)
		widgets["duration_timespan_radio"].connect("clicked", update_sensitive, widgets)
		widgets["duration_info_radio"].connect("clicked", update_sensitive, widgets)

		# translate labels
		window.set_title( _('Planned recording') )
		gui.get_object("browser_views_label3").set_markup( _('<b>Basic settings</b>') )
		gui.get_object("label14").set_text( _('Stream') )
		gui.get_object("label15").set_text( _('Folder') )
		gui.get_object("browser_views_label").set_markup( _('<b>Time</b>') )
		gui.get_object("label2").set_text( _('Day') )
		gui.get_object("label3").set_text( _('Month') )
		gui.get_object("label4").set_text( _('Year') )
		gui.get_object("label5").set_text( _('Hour') )
		gui.get_object("label11").set_text( _('Minute') )
		gui.get_object("label12").set_text( _('Second') )
		gui.get_object("label4").set_text( _('Year') )
		gui.get_object("label17").set_text( _('Name') )
		gui.get_object("browser_views_label1").set_markup( _('<b>Duration</b>') )
		gui.get_object("browser_views_label2").set_markup( _('<b>Repetition</b>') )
		gui.get_object("label7").set_text( _('minutes') )
		widgets["times_label"] = gui.get_object("label10")
		widgets["times_label"].set_text( _('times') )
		gui.get_object("label16").set_text( _('day(s)') )

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
			source = shell.get_property("selected_page")
			entry = RB.Source.get_entry_view(source)
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

	@staticmethod
	def find_by_ID(self, node, ID):
		if isinstance(node, Gtk.Buildable):
			if Gtk.Buildable.get_name(node) == ID:
				return node
		if isinstance(node, Gtk.Container):
			for child in node.get_children():
				found = self.find_by_ID(self, child, ID)
				if found:
					return found
		return None

	"""
	Activates the plugin on startup (basically just sets up the UI)
	"""
	def do_activate(self):
		shell = self.object
		app = shell.props.application
		# Load basic settings
		# Get the translation file
		install('rbrecord')
		# Store: stream name, dir, RecordProcess object, current song, recorded (num songs, size)
		self.record_db = Gtk.TreeStore(GObject.TYPE_STRING, GObject.TYPE_STRING, object, GObject.TYPE_STRING, GObject.TYPE_STRING)

		# load configuration
		self.config = configparser.RawConfigParser()
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
		self.plan = configparser.RawConfigParser()
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
		self.record_button_automatically_set = False
		self.btn_record = Gtk.ToggleButton(_("Record"))
		self.btn_record.connect('toggled', self.record_station)
		image_record = Gtk.Image()
		image_record.set_from_stock("gtk-media-record", Gtk.IconSize.BUTTON)
		self.btn_record.set_image(image_record)
		self.playbox = self.find_by_ID(self, shell.props.window, 'box3') # 'main-toolbar/box3/play-button'
		self.playbox.add(self.btn_record)

		# Set up plugin menu
		submenu = Gio.Menu()
		submenu.append(_("Planned recording ..."), "app.planned_recording")
		submenu.append(_("Record Manager"), "app.manage_dialog")
		app.add_plugin_menu_item('tools', 'plugin-record-station', Gio.MenuItem.new_submenu(_("Record"), submenu))

		# Set up actions
		self.action_record = Gio.SimpleAction.new_stateful('record_station', None, GLib.Variant.new_boolean(False))
		self.action_record.connect('activate', self.record_station)
		app.add_action(self.action_record)
		self.action_plan = Gio.SimpleAction.new('planned_recording', None)
		self.action_plan.connect('activate', self.planned_recording, False, False)
		app.add_action(self.action_plan)
		self.action_manager = Gio.SimpleAction.new('manage_dialog', None)
		self.action_manager.connect('activate', self.manage_dialog)
		app.add_action(self.action_manager)

		# Check if the source is Radio when starting and when source changes
		self.check_source(self, shell.get_property("selected-page"))
		self.source_list = shell.get_property("display-page-tree")
		self.source_list_id  = self.source_list.connect ('selected', self.check_source)

		# reload stream metadata every 1/2s
		GObject.timeout_add(500, self.update_station_info)

		# check for planned recordings every 1/2 s
		GObject.timeout_add(500, self.update_plan)

		# wait 1 second before loading the radio source, rhythmbox might not yet be ready
		GObject.timeout_add(1000, self.get_radio_source)

	def get_radio_source(self):
		shell = self.object
		db = shell.props.db
		# watch for selection changes to update the toolbar
		self.radio_source = shell.get_source_by_entry_type( db.entry_type_get_by_name("iradio") )
		return False

	"""
	Starts planned recordings, if available
	"""
	def update_plan(self):
		for item in self.plan.sections():
			timestamp = time.time()
			# event missed?
			if timestamp >= int(self.plan.get(item, "timestamp")) + 10:
				dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, _('Planned recording missed: ') + str(item) )
				dialog.set_title(_('Warning'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == Gtk.ResponseType.CLOSE:
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
				print("starting")
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
				rp = None
				i = 0
				for _item in self.record_db:
					if _item[2].uri == self.plan.get(item, "uri"):
						rp = _item[2]
						break
					i = i + 1
				if rp:
					if rp.song_num >= 2:
						# song info changed, recording finished
						self.update_plan_view()
						rp.stop(False)
						del self.record_db[i]
						if self.config.get("Interface", "show_notifications") == True:
							os.system("notify-send --icon=gtk-media-stop \"" + _('Automatic recording finished') + "\" \"" + item + "\"")
						if self.plan.get(item, "timestamp") == 9999999999:
							self.plan.remove_section(item)
			elif self.plan.get(item, "duration") == "manual_stop":
				pass
			else:
				# check if duration is over
				if time.time() >= int(self.plan.get(item, "duration")) + int(self.plan.get(item, "last_timestamp")):
					# get RecordProcess
					rp = None
					i = 0
					for _item in self.record_db:
						if _item[2].uri == self.plan.get(item, "uri"):
							rp = _item[2]
							break
						i = i + 1
					if rp:
						self.update_plan_view()
						rp.stop(False)
						del self.record_db[i]
						if self.config.get("Interface", "show_notifications") == True:
							os.system("notify-send --icon=gtk-media-stop \"" + _('Automatic recording finished') + "\" \"" + item + "\"")
						if self.plan.get(item, "timestamp") == 9999999999:
							self.plan.remove_section(item)

		# check if rhythmbox has been quit
		try:
			a = self.playbox
		except:
			return False
		return True


	"""
	Deactivates the plugin
	"""
	def do_deactivate(self):
		shell = self.object
		app = shell.props.application
		# Save configuration
		self.save_config()
		# Stop all rips on deactivation/quit
		self.stop_rip(None, True)
		if self.dialog_open == True:
			self.close_dialog(self.window)

		# Stop watching for source changes
		self.source_list.disconnect (self.source_list_id)

		# Clean the UIs
		self.playbox.remove(self.btn_record)
		app.remove_plugin_menu_item('tools', 'plugin-record-station')

		# Delete incomplete files
		if self.config.get("Ripping", "delete_incomplete") == True:
			for directory in self.cleanup:
				try:
					shutil.rmtree(directory)
				except:
					pass

		del self.action_record
		del self.action_plan
		del self.action_manager
		del self.btn_record
		del self.playbox
		del self.source_list
		del self.source_list_id
		self.record_button_automatically_set = False
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
		def ok_cb(widget, gui):
			# save
			self.config.set("Ripping", "use_defaultdir", gui.get_object("default_folder_checkbox").get_active() )
			self.config.set("Ripping", "defaultdir", gui.get_object("folder_choose_button").get_current_folder() )
			self.config.set("Ripping", "create_subfolder", gui.get_object("subfolder_checkbox").get_active() )
			self.config.set("Ripping", "delete_incomplete", gui.get_object("delete_incomplete_checkbox").get_active() )
			self.config.set("Ripping", "single_file", gui.get_object("single_file_checkbox").get_active() )
			self.config.set("Interface", "show_notifications", gui.get_object("notify_checkbox").get_active() )
			self.config.set("Interface", "show_manager", gui.get_object("show_checkbox").get_active() )
			self.config.set("Columns", "stream", gui.get_object("stream_checkbox").get_active() )
			self.config.set("Columns", "current_title", gui.get_object("current_title_checkbox").get_active() )
			self.config.set("Columns", "folder", gui.get_object("folder_checkbox").get_active() )
			self.config.set("Columns", "recorded", gui.get_object("recorded_checkbox").get_active() )
			self.config.set("Compability", "use_mplayer", gui.get_object("use_mplayer_cb").get_active() )
			self.config.set("Compability", "regexp", gui.get_object("regexp_entry").get_text() )
			# manage dialog may not be spawned, so just try
			try:
				self.update_columns()
			except:
				pass
			window.destroy()
		def cancel_cb(widget, data=None):
			window.destroy()
		def add_cb(widget):
			name = self.planned_recording(None, None, True, False)
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
				self.planned_recording(None, None, True, name)
				i = i - 1

		gui = Gtk.Builder()
		gui.add_from_file("preferences.glade")
		window = gui.get_object("preferences")
		window.set_title( _('Recording preferences') )

		# load widgets
		default_folder_checkbox = gui.get_object("default_folder_checkbox")
		folder_choose_button = gui.get_object("folder_choose_button")
		subfolder_checkbox = gui.get_object("subfolder_checkbox")
		delete_incomplete_checkbox = gui.get_object("delete_incomplete_checkbox")
		single_file_checkbox = gui.get_object("single_file_checkbox")
		notify_checkbox = gui.get_object("notify_checkbox")
		show_checkbox = gui.get_object("show_checkbox")
		stream_checkbox = gui.get_object("stream_checkbox")
		current_title_checkbox = gui.get_object("current_title_checkbox")
		folder_checkbox = gui.get_object("folder_checkbox")
		recorded_checkbox = gui.get_object("recorded_checkbox")
		ok_button = gui.get_object("ok_button")
		cancel_button = gui.get_object("cancel_button")
		add_button = gui.get_object("add_button")
		remove_button = gui.get_object("remove_button")
		edit_button = gui.get_object("edit_button")
		use_mplayer_checkbox = gui.get_object("use_mplayer_cb")
		regexp_entry = gui.get_object("regexp_entry")

		# load tree view
		view = gui.get_object("treeview1")
		selection = view.get_selection()
		self.plan_model = Gtk.ListStore(GObject.TYPE_STRING, GObject.TYPE_STRING)
		view.set_model( self.plan_model )
		# load columns
		rend_name = Gtk.CellRendererText()
		rend_name.set_property('editable', False)
		col_name = Gtk.TreeViewColumn( _('Name'), rend_name, text=0)
		rend_time = Gtk.CellRendererText()
		rend_time.set_property('editable', False)
		col_time = Gtk.TreeViewColumn( _('Time'), rend_time, text=1)
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
		ok_button.connect("clicked", ok_cb, gui)
		cancel_button.connect("clicked", cancel_cb)
		add_button.connect("clicked", add_cb)
		remove_button.connect("clicked", remove_cb, selection)
		edit_button.connect("clicked", edit_cb)
		use_mplayer_checkbox.set_active( bool(self.config.get("Compability", "use_mplayer")) )
		regexp_entry.set_text( str(self.config.get("Compability", "regexp")) )

		# load translations
		gui.get_object("browser_views_label").set_markup( _('<b>Folder</b>') )
		gui.get_object("browser_views_label1").set_markup( _('<b>Recording</b>') )
		gui.get_object("browser_views_label2").set_markup( _('<b>Interface</b>') )
		gui.get_object("browser_views_label3").set_markup( _('<b>Columns</b>') )
		gui.get_object("nb_label_2").set_text( _('Planned recordings') )
		gui.get_object("compability_label").set_text( _('Compability') )
		gui.get_object("label1").set_markup( _('<i>To improve compability with some streams (including mms:// streams), you can use mplayer as a backend instead of streamripper. However, track information and file splitting is not supported then.</i>') )
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
		if "RBIRadioSource" in type(source).__name__:
			self.btn_record.show()
		else:
			self.btn_record.hide()

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
		gui = Gtk.Builder()
		gui.add_from_file("dir_chooser.glade")
		self.filechoose = gui.get_object("filechooserdialog1")
		self.filechoose.set_title( _('Record Folder') )
		if self.config.get("Ripping", "defaultdir") != "":
			self.filechoose.set_current_folder(self.config.get("Ripping", "defaultdir"))
		else:
			self.filechoose.set_current_folder(os.path.expanduser("~"))

		self.filechoose.show()
		self.checkbox = gui.get_object("checkbox")
		self.checkbox.set_label( _('Do not ask again') )
		cancel_button = gui.get_object("cancel_button")
		cancel_button.connect("clicked", lambda x:self.filechoose.destroy())
		ok_button = gui.get_object("ok_button")
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
		shell = self.object
		source = shell.get_property("selected_page")
		entry = RB.Source.get_entry_view(source)
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
		shell = self.object
		if self.record_button_automatically_set:
			self.record_button_automatically_set = False
		else:
			if action.get_active():
				source = shell.get_property("selected_page")
				entry = RB.Source.get_entry_view(source)
				selected = entry.get_selected_entries()
				if selected != []:
					uri = selected[0].get_playback_uri()
					if self.config.get("Ripping", "use_defaultdir") == False:
						self.select_folder(uri)
					else:
						self.start_rip(None, uri, True, self.config.get("Ripping", "defaultdir"))
			else:
				source = shell.get_property("selected_page")
				entry = RB.Source.get_entry_view(source)
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

	"""
	Create record process
	returns: RecordProcess or None
	"""
	def start_rip(self, widget, uri, overrd, overrd_dir):
		# check if stream is already being recorded
		for entry in self.record_db:
			if entry[2].uri == uri:
				dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, _('This stream is already being recorded!'))
				dialog.set_title(_('Error'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == Gtk.ResponseType.CLOSE:
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
				except:
						pass

			# Terminate the subprocess Popen
			try:
				self.record_db[id][2].stop(self.config.get("Ripping", "delete_incomplete"))
				del self.record_db[id][2]
			except:
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
	def update_button_active(self, widget, stop_button, folder_button): # , playback_button):
		if widget.count_selected_rows() < 1:
			status = False
			#playback_button.set_sensitive(False)
		else:
			status = True
			#playback_button.set_sensitive(status)

			# playback is not possible with multiple selection
			#rows = self.tree_selection.get_selected_rows()
			#count = self.tree_selection.count_selected_rows()
			#if not count == 1:
			#	playback_button.set_sensitive(False)
			# playback is only possible with streamripper (not with mplayer)
			#id = rows[1][0]
			#try:
			#	self.record_db[id][2].relay_port
			#	playback_button.set_sensitive(True)
			#except:
			#	playback_button.set_sensitive(False)

		stop_button.set_sensitive(status)
		folder_button.set_sensitive(True)

	"""
	Update radio station info (stream name, song info) for the record manager
	"""
	def update_station_info(self):
		self.record_db.foreach(self.update_station_info_foreach)
		# check if rhythmbox has been quit
		try:
			a = self.playbox
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
				dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, _('This stream is already being recorded!'))
				dialog.set_title(_('Error'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == Gtk.ResponseType.CLOSE:
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
				dialog = Gtk.Dialog(_('Error'), None, 0, (Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, _('Try compability mode'), Gtk.ResponseType.OK) )
				dialog.get_content_area().pack_start( Gtk.Label( _('Could not record the stream! Do you want\n to record it in compability mode?\n\n') + process.uri ) )
				dialog.show_all()
				if dialog.run() == Gtk.ResponseType.OK:
					self.record_compability_mode(process.uri)
				dialog.destroy()
			else:
				dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, _('Could not record the stream in compability mode! Please check that it is valid:\n\n') + process.uri)
				dialog.set_title(_('Error'))
				dialog.set_property("skip-taskbar-hint", False)
				if dialog.run() == Gtk.ResponseType.CLOSE:
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
		if not (recorded_info == self.record_db[path][4]):
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
		shell = self.object
		db = shell.props.db
		player = shell.get_property("shell-player")
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
		db_entry_type = RecordingEntryType()
		db_entry_type.category = RB.RhythmDBEntryCategory.STREAM
		db.register_entry_type(db_entry_type)
		db_entry = db.entry_lookup_by_location("http://localhost:" + str(relay_port))
		if db_entry == None:
			db_entry = RB.RhythmDBEntry.new(db, db_entry_type, "http://localhost:" + str(relay_port))
		# set entry name
		db.entry_set(db_entry, RB.RhythmDBPropType.TITLE, name) 
		db.commit()

		# play
		player.play_entry(db_entry, shell.get_property("selected_page"))

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
	def manage_dialog(self, action, widget=None):
		if self.dialog_open == False:
			self.dialog_open = True
			# Create the Manager window
			gui = Gtk.Builder()
			gui.add_from_file("manage.glade")
			self.window = gui.get_object("window1")
			self.window.set_position(Gtk.WindowPosition.CENTER)
			self.window.set_title( _('Manage recordings') )
			self.window.show()
			self.window.connect("delete_event", self.close_dialog)

			# Setup the tree view
			self.view = gui.get_object("treeview")
			self.view.set_model(self.record_db)

			# initialize toolbar
			toolbar = gui.get_object("toolbar1")
			stop_button = Gtk.ToolButton(Gtk.STOCK_STOP)
			stop_button.set_label (_('Stop recording'))
			stop_button.set_tooltip_text (_('Stop recording'))
			stop_button.connect("clicked", self.stop_rip)
			toolbar.insert(stop_button, -1)

			folder_button = Gtk.ToolButton(Gtk.STOCK_OPEN)
			folder_button.set_label(_('Open folder'))
			folder_button.set_tooltip_text (_('Open folder'))
			folder_button.connect("clicked", self.open_folder)
			toolbar.insert(folder_button, -1)

			#deactivated: buggy and unknown functionality
			#playback_button = Gtk.ToolButton(Gtk.STOCK_MEDIA_PLAY)
			#playback_button.connect("clicked", self.play_relay)
			#playback_button.set_tooltip_text (_('Play'))
			#toolbar.insert(playback_button, -1)

			self.tree_selection = self.view.get_selection()
			self.tree_selection.set_mode(Gtk.SelectionMode.MULTIPLE)
			# change button "active" status when selection changes
			self.tree_selection.connect("changed", self.update_button_active, stop_button, folder_button) #, playback_button)
			self.update_button_active(self.tree_selection, stop_button, folder_button) #, playback_button)

			# initialize buttons
			preferences_button = gui.get_object("preferences_button")
			preferences_button.connect("clicked", self.create_configure_dialog)
			close_button = gui.get_object("close_button")
			close_button.connect("clicked", self.close_dialog)

			# initialize treeview
			# Use pango to render text so it is not oversized
			rend_uri = Gtk.CellRendererText()
			rend_uri.set_property("editable", False)
			rend_uri.set_property("ellipsize",Pango.EllipsizeMode.END)
			rend_dir = Gtk.CellRendererText()
			rend_dir.set_property("editable", False)
			rend_dir.set_property("ellipsize",Pango.EllipsizeMode.END)
			rend_song = Gtk.CellRendererText()
			rend_song.set_property("editable", False)
			rend_song.set_property("ellipsize",Pango.EllipsizeMode.END)
			rend_recorded = Gtk.CellRendererText()
			rend_recorded.set_property("editable", False)
			rend_recorded.set_property("ellipsize",Pango.EllipsizeMode.END)

			self.col_uri = Gtk.TreeViewColumn( _('Stream'), rend_uri, text=0)
			self.col_uri.set_resizable(True)
			self.col_uri.set_expand(True)
			self.col_dir = Gtk.TreeViewColumn( _('Directory'), rend_dir, text=1)
			self.col_dir.set_resizable(True)
			self.col_dir.set_expand(True)
			self.col_song = Gtk.TreeViewColumn( _('Current title'), rend_dir, text=3)
			self.col_song.set_resizable(True)
			self.col_song.set_expand(True)
			self.col_recorded = Gtk.TreeViewColumn( _('Recorded'), rend_dir, text=4)
			self.col_recorded.set_resizable(True)
			self.col_recorded.set_expand(True)

			# update show/hide of TreeView columns
			self.update_columns()
			self.window.show_all()
		else:
			self.window.present()

		# Delete obsolete rip processes
		self.stop_rip(None, True, True)

class RecordingEntryType(RB.RhythmDBEntryType):
	def __init__(self):
		RB.RhythmDBEntryType.__init__(self, name='recording-entry-type')

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
		except OSError as e:
			print((_('MPlayer binary not found! ERROR: %s') % e))
			dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, _('MPlayer not found!\nPlease install the mplayer package from your distribution or install it manually from: http://www.mplayerhq.hu'))
			dialog.set_title(_('Missing binary file'))
			dialog.set_property("skip-taskbar-hint", False)
			if dialog.run() == Gtk.ResponseType.CLOSE:
				dialog.destroy()

			self.killed = True
			return False

		threading.Thread(target=self.reload_info).start()

	"""
	Refresh file size
	"""
	def reload_info(self):
		while self.process.poll()==None:
			try:
				self.song_size = os.path.getsize(self.directory + "/" + self.filename) / 1000
			except:
				self.song_size = 0
			line = ""
			while True:
				try:
					char = str(pout.read(1), encoding='UTF-8')
				except:
					break

				if char == None or char == "":
					break

				if char == "\n":
					break
				if char == "\r":
					break
				line = line+char
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
		except OSError as e:
			print((_('Streamripper binary not found! ERROR: %s') % e))
			dialog = Gtk.MessageDialog(None, Gtk.DialogFlags.MODAL | Gtk.DialogFlags.DESTROY_WITH_PARENT, Gtk.MessageType.ERROR, Gtk.ButtonsType.CLOSE, _('Streamripper not found!\nPlease install the streamripper package from your distribution or install it manually from: http://streamripper.sourceforge.net'))
			dialog.set_title(_('Missing binary file'))
			dialog.set_property("skip-taskbar-hint", False)
			if dialog.run() == Gtk.ResponseType.CLOSE:
				dialog.destroy()

			self.killed = True
			return False
		threading.Thread(target=self.reload_info).start()

	"""
	Reload song info etc.
	"""
	def reload_info(self):
		pout = self.process.stdout
		while self.process.poll()==None:
			line = ""

			while True:
				try:
					char = str(pout.read(1), encoding='UTF-8')
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
