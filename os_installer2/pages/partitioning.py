#!/bin/true
# -*- coding: utf-8 -*-
#
#  This file is part of os-installer
#
#  Copyright 2013-2016 Ikey Doherty <ikey@solus-project.com>
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 2 of the License, or
#  (at your option) any later version.
#

from .basepage import BasePage
from os_installer2 import format_size_local, MIN_REQUIRED_SIZE
from os_installer2.strategy import DualBootStrategy
from os_installer2.strategy import ReplaceOSStrategy
from os_installer2.strategy import EmptyDiskStrategy
from os_installer2.strategy import WipeDiskStrategy
from os_installer2.strategy import UserPartitionStrategy
from os_installer2.diskman import SystemPartition, DriveProber
from gi.repository import Gtk, GLib
import sys
import os
import threading


INDEX_PARTITION_PATH = 0
INDEX_PARTITION_TYPE = 1
INDEX_PARTITION_DESCRIPTION = 2
INDEX_PARTITION_FORMAT = 3
INDEX_PARTITION_MOUNT_AS = 4
INDEX_PARTITION_SIZE = 5
INDEX_PARTITION_FREE_SPACE = 6
INDEX_PARTITION_OBJECT = 7
INDEX_PARTITION_SIZE_NUM = 8

ACCEPTABLE_FS_TYPES = ["ext", "ext2", "ext3", "ext4"]


class ManualPage(Gtk.VBox):
    """ Manual partitioning page, mostly TreeView with gparted proxy """

    info = None
    store_mountpoints = None
    selection_label = None

    selection_home = None
    selection_root = None
    selection_root_size = None
    selection_swap = None
    cur_strategy = None

    def __init__(self):
        Gtk.VBox.__init__(self)

        lab = Gtk.Label("Select custom mount points to use with Solus from "
                        "the available partition selection below.\n"
                        "Only available system partitions and swap will be "
                        "displayed here. Use gparted to edit partitions\nin "
                        "order for them to be displayed.")
        self.pack_start(lab, False, False, 0)
        lab.set_margin_top(20)
        lab.set_margin_bottom(20)
        lab.set_halign(Gtk.Align.START)

        self.selection_label = Gtk.Label("")
        self.selection_label.set_margin_bottom(5)
        self.pack_start(self.selection_label, False, False, 0)
        self.selection_label.set_halign(Gtk.Align.START)

        self.store_mountpoints = Gtk.ListStore(str, str)
        self.store_mountpoints.append(["/", "/"])
        self.store_mountpoints.append(["/home", "/home"])
        self.store_mountpoints.append(["swap", "swap"])
        self.store_mountpoints.append([None, None])

        self.treeview = Gtk.TreeView()
        self.scrl = Gtk.ScrolledWindow(None, None)
        self.scrl.add(self.treeview)
        self.set_border_width(12)
        self.scrl.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrl.set_shadow_type(Gtk.ShadowType.ETCHED_IN)
        sd = Gtk.JunctionSides.BOTTOM
        self.scrl.get_style_context().set_junction_sides(sd)
        self.pack_start(self.scrl, True, True, 0)

        # device
        ren = Gtk.CellRendererText()
        self.column3 = Gtk.TreeViewColumn("Device", ren)
        self.column3.add_attribute(ren, "markup", INDEX_PARTITION_PATH)
        self.treeview.append_column(self.column3)

        self.column4 = Gtk.TreeViewColumn("Current filesystem", ren)
        self.column4.add_attribute(ren, "markup", INDEX_PARTITION_TYPE)
        self.treeview.append_column(self.column4)

        # description
        ren = Gtk.CellRendererText()
        self.column5 = Gtk.TreeViewColumn("Operating system", ren)
        self.column5.add_attribute(ren, "markup", INDEX_PARTITION_DESCRIPTION)
        self.treeview.append_column(self.column5)

        # mount point
        ren = Gtk.CellRendererCombo()
        ren.set_property("editable", True)
        ren.set_property("model", self.store_mountpoints)
        ren.set_property("has-entry", False)
        ren.set_property("text-column", 0)
        ren.connect("edited", self.on_mount_changed)
        self.column6 = Gtk.TreeViewColumn("Mount point", ren, text=4)
        self.treeview.append_column(self.column6)

        # format
        ren = Gtk.CellRendererToggle()
        ren.connect("toggled", self.on_format_toggled)
        self.column7 = Gtk.TreeViewColumn("Format", ren,
                                          active=INDEX_PARTITION_FORMAT)
        self.treeview.append_column(self.column7)

        # size
        ren = Gtk.CellRendererText()
        self.column8 = Gtk.TreeViewColumn("Size", ren)
        self.column8.add_attribute(ren, "markup", INDEX_PARTITION_SIZE)
        self.treeview.append_column(self.column8)

        # Used space
        ren = Gtk.CellRendererText()
        self.column9 = Gtk.TreeViewColumn("Free space", ren)
        self.column9.add_attribute(ren, "markup", INDEX_PARTITION_FREE_SPACE)
        self.treeview.append_column(self.column9)

        toolbar = Gtk.Toolbar()
        toolbar.get_style_context().add_class(Gtk.STYLE_CLASS_INLINE_TOOLBAR)
        junctions = Gtk.JunctionSides.TOP
        toolbar.get_style_context().set_junction_sides(junctions)

        gparted = Gtk.ToolButton()
        gparted.set_label("Launch Partition Editor")
        gparted.connect("clicked", self.launch_gparted)
        gparted.set_is_important(True)
        toolbar.add(gparted)
        self.pack_start(toolbar, False, False, 0)

    def on_format_toggled(self, widget, path):
        model = self.treeview.get_model()
        row = model[path]
        mpoint = row[INDEX_PARTITION_MOUNT_AS]
        if mpoint not in ['/home', 'swap']:
            return
        acceptables = {
            '/home': ACCEPTABLE_FS_TYPES,
            'swap': ['swap']
        }
        # Don't allow overriding the forced format.
        fs = row[INDEX_PARTITION_TYPE]
        if fs not in acceptables[mpoint]:
            return

        row[INDEX_PARTITION_FORMAT] = not row[INDEX_PARTITION_FORMAT]

    def launch_gparted(self, btn, udata=None):
        """ Send off a thread """
        self.info.owner.set_sensitive(False)
        t = threading.Thread(target=self._launch_gparted)
        t.start()

    def _launch_gparted(self):
        """ Launch this on the thread so the UI doesnt lock """
        perms = self.info.owner.get_perms_manager()
        perms.up_permissions()
        try:
            os.system("gparted")
        except:
            pass

        perms = self.info.owner.get_perms_manager()
        dm = self.info.owner.get_disk_manager()

        prober = DriveProber(dm)
        self.info.prober = prober
        self.info.prober.probe()
        perms.down_permissions()
        self.info.invalidated = True
        self.selection_root = None
        self.selection_home = None
        self.selection_swap = None

        GLib.idle_add(self.restore_ui)

    def restore_ui(self):
        self.info.owner.set_sensitive(True)
        self.queue_draw()
        self.populate_ui()
        self.update_selection()
        # TODO: Refresh

    def on_mount_changed(self, widget, path, text):
        print("{} = {}".format(path, text))
        model = self.treeview.get_model()

        if text is None or text.strip() == '':
            self.nullify_selection(path)
            return

        model[path][4] = text

        if text == '/':
            self.set_root_partition(path)
        elif text == 'swap':
            self.set_swap_partition(path)
        elif text == '/home':
            self.set_home_partition(path)

        self.update_selection()

    def set_root_partition(self, path):
        """ Update the root partition """
        model = self.treeview.get_model()
        row = model[path]
        active_part = row[INDEX_PARTITION_PATH]
        self.selection_root = active_part
        self.selection_root_size = row[INDEX_PARTITION_SIZE_NUM]
        for p in model:
            skip_part = p[INDEX_PARTITION_PATH]
            skip_mount = p[INDEX_PARTITION_MOUNT_AS]
            if skip_part == active_part:
                # Mandatory format of /
                p[INDEX_PARTITION_FORMAT] = True
                continue
            # Reset anyone trying to be root..
            if skip_mount == '/':
                p[INDEX_PARTITION_MOUNT_AS] = None
                p[INDEX_PARTITION_FORMAT] = False
                if self.selection_home == active_part:
                    self.selection_home = None
                if self.selection_swap == active_part:
                    self.selection_swap = None

    def set_swap_partition(self, path):
        """ Update the swap partition """
        model = self.treeview.get_model()
        row = model[path]
        active_part = row[INDEX_PARTITION_PATH]
        self.selection_swap = active_part
        fs = row[INDEX_PARTITION_TYPE]
        if fs != "swap":
            row[INDEX_PARTITION_FORMAT] = True
        for p in model:
            skip_part = p[INDEX_PARTITION_PATH]
            skip_mount = p[INDEX_PARTITION_MOUNT_AS]
            if skip_part == active_part:
                continue
            # Reset anyone trying to be swap..
            if skip_mount == 'swap':
                p[INDEX_PARTITION_MOUNT_AS] = None
                p[INDEX_PARTITION_FORMAT] = False
                if self.selection_home == active_part:
                    self.selection_home = None
                if self.selection_root == active_part:
                    self.selection_root = None

    def nullify_selection(self, path):
        allowed = ['/', '/home', 'swap']

        model = self.treeview.get_model()
        row = model[path]
        sel_for = row[INDEX_PARTITION_MOUNT_AS]
        if sel_for not in allowed:
            return
        row[INDEX_PARTITION_MOUNT_AS] = None
        row[INDEX_PARTITION_FORMAT] = False
        if sel_for == '/':
            self.selection_root = None
        elif sel_for == '/home':
            self.selection_home = None
        else:
            self.selection_swap = None
        self.update_selection()

    def set_home_partition(self, path):
        """ Update the home partition """
        model = self.treeview.get_model()
        row = model[path]
        active_part = row[INDEX_PARTITION_PATH]
        self.selection_home = active_part
        fs = row[INDEX_PARTITION_TYPE]
        if fs not in ACCEPTABLE_FS_TYPES:
            row[INDEX_PARTITION_FORMAT] = True
        for p in model:
            skip_part = p[INDEX_PARTITION_PATH]
            skip_mount = p[INDEX_PARTITION_MOUNT_AS]
            if skip_part == active_part:
                continue
            # Reset anyone trying to be /home..
            if skip_mount == '/home':
                p[INDEX_PARTITION_MOUNT_AS] = None
                p[INDEX_PARTITION_FORMAT] = False
                if self.selection_swap == active_part:
                    self.selection_swap = None
                if self.selection_root == active_part:
                    self.selection_root = None

    def push_partition(self, drive, part):
        model = self.treeview.get_model()
        os = None
        if part.path in drive.operating_systems:
            os = drive.operating_systems[part.path].name

        fs = part.partition.fileSystem
        fsname = None
        if fs and fs.type:
            fsname = fs.type

        partSizeActual = part.partition.getLength() * \
            part.partition.disk.device.sectorSize
        model.append([
            part.path,
            fsname,
            os,
            False,
            None,
            part.sizeString,
            part.freespace_string,
            part,
            partSizeActual
        ])
        """
        INDEX_PARTITION_PATH = 0
        INDEX_PARTITION_TYPE = 1
        INDEX_PARTITION_DESCRIPTION = 2
        INDEX_PARTITION_FORMAT = 3
        INDEX_PARTITION_MOUNT_AS = 4
        INDEX_PARTITION_SIZE = 5
        INDEX_PARTITION_FREE_SPACE = 6
        INDEX_PARTITION_OBJECT = 7
        INDEX_PARTITION_SIZE_NUM = 8
        """

    def push_swap(self, part):
        model = self.treeview.get_model()

        partSizeActual = part.getLength() * part.disk.device.sectorSize
        partSize = format_size_local(partSizeActual)
        model.append([
            part.path,
            "swap",
            None,
            False,
            None,
            partSize,
            None,
            None,
            partSizeActual
        ])

    def populate_ui(self):
        prober = self.info.prober

        model = Gtk.ListStore(str, str, str, bool,
                              str, str, str, SystemPartition, long)
        self.treeview.set_model(model)
        for drive in prober.drives:
            for swap in drive.get_swap_partitions():
                try:
                    print(swap)
                    self.push_swap(swap)
                except Exception as e:
                    print("Swap problem: {}".format(e))

            for part in sorted(drive.partitions):
                try:
                    part_prop = drive.partitions[part]
                    self.push_partition(drive, part_prop)
                except Exception as e:
                    print("Init problem: {}".format(e))
            print(drive)

    def update_strategy(self, info):
        self.info = info
        info.owner.set_can_next(False)
        if self.info.strategy != self.cur_strategy:
            self.populate_ui()
        self.cur_strategy = self.info.strategy
        self.update_selection()

    def update_selection(self):
        """ Test if we can move forward now, i.e. everything is valid... """

        string_sets = [
            (self.selection_root, "<b>Root partition:</b> {}"),
            (self.selection_home, "<b>Home partition:</b> {}"),
            (self.selection_swap, "<b>Swap partition:</b> {}")
        ]

        lab = []

        for sel, display in string_sets:
            if not sel:
                continue
            if sel == "":
                continue
            lab.append(display.format(sel))
        labe = "\t\t".join(lab)

        # Don't allow forward
        if not self.selection_root:
            self.info.owner.set_can_next(False)
            self.selection_label.set_markup(labe)
            return

        # Can't go forward so nuh
        if self.selection_root_size < MIN_REQUIRED_SIZE:
            labe += "\n<b>Root partition is not at least 10GB</b>"
            self.selection_label.set_markup(labe)
            self.info.owner.set_can_next(False)
            return

        # Now we can go forward.
        self.selection_label.set_markup(labe)
        self.info.owner.set_can_next(True)


class DualBootPage(Gtk.VBox):
    """ Used to manage the dual boot configuration settings,
        essentially we're just here to resize the users partititon
        and make room for Solus. """

    image = None
    label = None
    spin = None
    info_label = None
    size_label = None
    info = None

    def __init__(self):
        Gtk.VBox.__init__(self)

        self.set_border_width(40)

        self.info_label = Gtk.Label.new("")
        self.pack_start(self.info_label, False, False, 0)
        self.info_label.set_margin_bottom(10)
        self.info_label.set_halign(Gtk.Align.START)

        # Construct dual-boot row
        hbox = Gtk.HBox(0)
        hbox.set_margin_top(20)
        self.pack_start(hbox, False, False, 0)

        self.image = Gtk.Image.new()
        self.image.set_margin_end(12)
        hbox.pack_start(self.image, False, False, 0)

        self.label = Gtk.Label.new("")
        self.label.set_margin_end(20)
        self.label.set_halign(Gtk.Align.START)
        hbox.pack_start(self.label, False, False, 0)

        self.spin = Gtk.SpinButton.new_with_range(0, 1000, 10)
        self.spin.connect("value-changed", self.on_value_changed)
        hbox.pack_start(self.spin, False, False, 5)
        lab = Gtk.Label.new("GB")
        hbox.pack_start(lab, False, False, 1)
        lab.set_halign(Gtk.Align.START)

        lab2 = Gtk.Label.new("New size for your existing installation")
        lab2.set_margin_start(20)
        hbox.pack_start(lab2, False, False, 4)
        lab2.get_style_context().add_class("dim-label")

        # Now start our row
        hbox = Gtk.HBox(0)
        hbox.set_margin_top(20)
        self.pack_start(hbox, False, False, 0)

        # our icon
        sz = Gtk.IconSize.DIALOG
        image = Gtk.Image.new_from_icon_name("distributor-logo-solus", sz)
        image.set_pixel_size(64)
        image.set_margin_end(12)
        hbox.pack_start(image, False, False, 0)

        # our label
        label = Gtk.Label.new("<big>New Solus Installation</big>")
        label.set_use_markup(True)
        label.set_margin_end(20)
        label.set_halign(Gtk.Align.START)
        hbox.pack_start(label, False, False, 0)

        self.size_label = Gtk.Label.new("0GB")
        self.size_label.set_margin_start(20)
        hbox.pack_start(self.size_label, False, False, 4)

    def on_value_changed(self, spin, w=None):
        if not self.info:
            return

        val = self.spin.get_value()
        avail = self.info.strategy.candidate_part.size
        GB = 1000.0 * 1000.0 * 1000.0

        nval = (avail / GB) - val
        ssize = format_size_local(nval * GB, double_precision=True)
        self.size_label.set_markup(ssize)

        self.info.strategy.set_our_size(nval * GB)
        self.info.strategy.set_their_size(avail - (nval * GB))

    def update_strategy(self, info):
        self.info = info
        info.owner.set_can_next(True)
        os = info.strategy.sel_os
        self.image.set_from_icon_name(os.icon_name, Gtk.IconSize.DIALOG)
        self.image.set_pixel_size(64)
        self.label.set_markup("<big>{}</big>".format(os.name))

        used = info.strategy.candidate_part.min_size
        avail = info.strategy.candidate_part.size

        GB = 1000.0 * 1000.0 * 1000.0
        min_gb = MIN_REQUIRED_SIZE
        dmin = float(used / GB)
        dmax = float((avail - min_gb) / GB)
        # Set upper minimum size for the new Solus

        adju = Gtk.Adjustment.new(dmin, dmin, dmax, 1, 10, 0)
        self.spin.set_adjustment(adju)
        self.spin.set_digits(2)

        os_name = os.name
        # We need this much
        min_we_needs = format_size_local(min_gb, double_precision=True)
        # They need this much
        min_they_needs = format_size_local(used, double_precision=True)
        # Total of this much
        max_avail = format_size_local(avail - used, double_precision=True)
        total_size = format_size_local(avail, double_precision=True)

        l = "Resize the partition containing {} to make room for the " \
            "new Solus installation.\n" \
            "Solus requires a minimum of {} disk space for the installation" \
            ", so free up <b>at least {}</b>\nfrom the maximum available " \
            "{}\n{} will require a minimum of {} from the total {}".format(
                os_name, min_we_needs, min_we_needs, max_avail,
                "Your currently installed operating system", min_they_needs,
                total_size)
        self.info_label.set_markup(l)


class InstallerPartitioningPage(BasePage):
    """ Dual boot + partitioning page """

    info = None
    stack = None

    # Dual boot page
    dbpage = None
    mpage = None

    def __init__(self):
        BasePage.__init__(self)
        self.stack = Gtk.Stack()
        # Reduce lag
        self.stack.set_transition_type(Gtk.StackTransitionType.NONE)
        self.pack_start(self.stack, True, True, 0)

        # Slow computers might show this page.. blank it
        label = Gtk.Label.new("")
        label.set_valign(Gtk.Align.CENTER)
        label.set_halign(Gtk.Align.CENTER)
        self.stack.add_named(label, "automatic")

        self.dbpage = DualBootPage()
        self.stack.add_named(self.dbpage, "dual-boot")

        self.mpage = ManualPage()
        self.stack.add_named(self.mpage, "manual")

        self.stack.set_visible_child_name("automatic")

    def get_title(self):
        return "Configure disks"

    def get_name(self):
        return "partitioning"

    def get_icon_name(self):
        return "drive-multidisk-symbolic"

    def prepare(self, info):
        self.info = info

        # Serious sanity stuffs
        if not info.strategy:
            print("FATAL: No strategy")
            sys.exit(0)

        skips = [
            EmptyDiskStrategy,
            WipeDiskStrategy,
            ReplaceOSStrategy,
        ]
        for sk in skips:
            if isinstance(info.strategy, sk):
                self.stack.set_visible_child_name("automatic")
                self.info.owner.skip_page()
                return
        if isinstance(info.strategy, DualBootStrategy):
            self.stack.set_visible_child_name("dual-boot")
            self.dbpage.update_strategy(info)
        elif isinstance(info.strategy, UserPartitionStrategy):
            self.mpage.update_strategy(info)
            self.stack.set_visible_child_name("manual")
        else:
            print("FATAL: Unknown strategy type!")
            sys.exit(0)
