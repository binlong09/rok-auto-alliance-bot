#!/usr/bin/env python3
import os
import tkinter as tk
from tkinter import ttk, messagebox
import logging
from instance_manager import InstanceManager


class InstanceManagerDialog:
    """Dialog for managing multiple BlueStacks instances"""

    def __init__(self, parent, instance_manager, callback=None):
        self.parent = parent
        self.instance_manager = instance_manager
        self.callback = callback  # Callback function when an instance is selected

        self.logger = logging.getLogger(__name__)

        # Create a top-level dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Instance Manager")
        self.dialog.geometry("600x500")
        self.dialog.resizable(True, True)
        self.dialog.transient(parent)  # Set as transient to parent window
        self.dialog.grab_set()  # Make dialog modal

        # Dialog was closed via window close button
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_cancel)

        # Variables
        self.current_instance_id = None
        self.instances = []

        # UI Elements
        self.create_widgets()

        # Load instances
        self.load_instances()

    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.dialog, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Instances list frame
        list_frame = ttk.LabelFrame(main_frame, text="BlueStacks Instances", padding="10")
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Treeview for instances
        columns = ("name", "bluestacks", "port", "description")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings", selectmode="browse")

        # Define headings
        self.tree.heading("name", text="Name")
        self.tree.heading("bluestacks", text="BlueStacks Instance")
        self.tree.heading("port", text="ADB Port")
        self.tree.heading("description", text="Description")

        # Define columns
        self.tree.column("name", width=150)
        self.tree.column("bluestacks", width=150)
        self.tree.column("port", width=80)
        self.tree.column("description", width=200)

        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        # Pack
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind selection event
        self.tree.bind("<<TreeviewSelect>>", self.on_instance_select)

        # Buttons frame
        buttons_frame = ttk.Frame(main_frame)
        buttons_frame.pack(fill=tk.X, pady=10)

        # Action buttons
        self.new_button = ttk.Button(buttons_frame, text="New Instance", command=self.on_new_instance)
        self.new_button.pack(side=tk.LEFT, padx=5)

        self.edit_button = ttk.Button(buttons_frame, text="Edit Instance", command=self.on_edit_instance,
                                      state=tk.DISABLED)
        self.edit_button.pack(side=tk.LEFT, padx=5)

        self.duplicate_button = ttk.Button(buttons_frame, text="Duplicate", command=self.on_duplicate_instance,
                                           state=tk.DISABLED)
        self.duplicate_button.pack(side=tk.LEFT, padx=5)

        self.delete_button = ttk.Button(buttons_frame, text="Delete", command=self.on_delete_instance,
                                        state=tk.DISABLED)
        self.delete_button.pack(side=tk.LEFT, padx=5)

        # Dialog buttons
        dialog_buttons = ttk.Frame(main_frame)
        dialog_buttons.pack(fill=tk.X, pady=5)

        self.select_button = ttk.Button(dialog_buttons, text="Select", command=self.on_select, state=tk.DISABLED)
        self.select_button.pack(side=tk.RIGHT, padx=5)

        self.cancel_button = ttk.Button(dialog_buttons, text="Cancel", command=self.on_cancel)
        self.cancel_button.pack(side=tk.RIGHT, padx=5)

    def load_instances(self):
        """Load instances into treeview"""
        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Get instances from manager
        self.instances = self.instance_manager.get_all_instances()

        # Get current instance
        current_instance = self.instance_manager.get_current_instance()
        if current_instance:
            self.current_instance_id = current_instance["id"]

        # Add instances to treeview
        for instance in self.instances:
            values = (
                instance["name"],
                instance["bluestacks_instance"],
                instance["adb_port"],
                instance["description"]
            )
            item_id = self.tree.insert("", tk.END, values=values)

            # Select current instance
            if instance["id"] == self.current_instance_id:
                self.tree.selection_set(item_id)

        # If we have a current instance but it wasn't selected, select the first item
        if not self.tree.selection() and self.tree.get_children():
            self.tree.selection_set(self.tree.get_children()[0])
            self.on_instance_select(None)  # Trigger selection event

    def get_selected_instance_id(self):
        """Get the ID of the currently selected instance"""
        selection = self.tree.selection()
        if not selection:
            return None

        item = selection[0]
        idx = self.tree.index(item)

        if idx < 0 or idx >= len(self.instances):
            return None

        return self.instances[idx]["id"]

    def on_instance_select(self, event):
        """Handle instance selection"""
        instance_id = self.get_selected_instance_id()

        if instance_id:
            self.edit_button.config(state=tk.NORMAL)
            self.duplicate_button.config(state=tk.NORMAL)
            self.select_button.config(state=tk.NORMAL)

            # Only enable delete if there's more than one instance
            if len(self.instances) > 1:
                self.delete_button.config(state=tk.NORMAL)
            else:
                self.delete_button.config(state=tk.DISABLED)
        else:
            self.edit_button.config(state=tk.DISABLED)
            self.duplicate_button.config(state=tk.DISABLED)
            self.select_button.config(state=tk.DISABLED)
            self.delete_button.config(state=tk.DISABLED)

    def on_new_instance(self):
        """Create a new instance"""
        dialog = InstanceEditDialog(self.dialog, "New Instance", callback=self.on_instance_created)
        self.dialog.wait_window(dialog.dialog)

    def on_instance_created(self, name, bluestacks_instance, adb_port, description):
        """Callback when a new instance is created"""
        try:
            instance_id = self.instance_manager.create_instance(
                name=name,
                bluestacks_instance=bluestacks_instance,
                adb_port=adb_port,
                description=description
            )

            if instance_id:
                self.load_instances()

                # Select the new instance
                for i, instance in enumerate(self.instances):
                    if instance["id"] == instance_id:
                        item = self.tree.get_children()[i]
                        self.tree.selection_set(item)
                        self.on_instance_select(None)
                        break
        except Exception as e:
            self.logger.error(f"Error creating instance: {e}")
            messagebox.showerror("Error", f"Failed to create instance: {e}")

    def on_edit_instance(self):
        """Edit the selected instance"""
        instance_id = self.get_selected_instance_id()
        if not instance_id:
            return

        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            messagebox.showerror("Error", "Instance not found")
            return

        dialog = InstanceEditDialog(
            self.dialog,
            "Edit Instance",
            name=instance["name"],
            bluestacks_instance=instance["bluestacks_instance"],
            adb_port=instance["adb_port"],
            description=instance["description"],
            callback=lambda name, bs, port, desc: self.on_instance_updated(instance_id, name, bs, port, desc)
        )
        self.dialog.wait_window(dialog.dialog)

    def on_instance_updated(self, instance_id, name, bluestacks_instance, adb_port, description):
        """Callback when an instance is updated"""
        try:
            success = self.instance_manager.update_instance(
                instance_id=instance_id,
                name=name,
                bluestacks_instance=bluestacks_instance,
                adb_port=adb_port,
                description=description
            )

            if success:
                self.load_instances()
        except Exception as e:
            self.logger.error(f"Error updating instance: {e}")
            messagebox.showerror("Error", f"Failed to update instance: {e}")

    def on_duplicate_instance(self):
        """Duplicate the selected instance"""
        instance_id = self.get_selected_instance_id()
        if not instance_id:
            return

        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            messagebox.showerror("Error", "Instance not found")
            return

        # Ask for a new name
        new_name = f"Copy of {instance['name']}"
        dialog = InstanceNameDialog(self.dialog, "Duplicate Instance", new_name,
                                    lambda name: self.on_instance_duplicated(instance_id, name))
        self.dialog.wait_window(dialog.dialog)

    def on_instance_duplicated(self, instance_id, new_name):
        """Callback when an instance is duplicated"""
        try:
            new_instance_id = self.instance_manager.duplicate_instance(instance_id, new_name)

            if new_instance_id:
                self.load_instances()

                # Select the new instance
                for i, instance in enumerate(self.instances):
                    if instance["id"] == new_instance_id:
                        item = self.tree.get_children()[i]
                        self.tree.selection_set(item)
                        self.on_instance_select(None)
                        break
        except Exception as e:
            self.logger.error(f"Error duplicating instance: {e}")
            messagebox.showerror("Error", f"Failed to duplicate instance: {e}")

    def on_delete_instance(self):
        """Delete the selected instance"""
        instance_id = self.get_selected_instance_id()
        if not instance_id:
            return

        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            messagebox.showerror("Error", "Instance not found")
            return

        # Confirm deletion
        if messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete instance '{instance['name']}'?"):
            try:
                success = self.instance_manager.delete_instance(instance_id)

                if success:
                    self.load_instances()
            except Exception as e:
                self.logger.error(f"Error deleting instance: {e}")
                messagebox.showerror("Error", f"Failed to delete instance: {e}")

    def on_select(self):
        """Select the current instance and close dialog"""
        instance_id = self.get_selected_instance_id()
        if not instance_id:
            return

        # Set as current instance
        self.instance_manager.set_current_instance(instance_id)

        # Call callback if provided
        if self.callback:
            self.callback(instance_id)

        self.dialog.destroy()

    def on_cancel(self):
        """Cancel and close dialog"""
        self.dialog.destroy()


class InstanceEditDialog:
    """Dialog for editing instance details"""

    def __init__(self, parent, title, name="", bluestacks_instance="Nougat64", adb_port="5555",
                 description="", callback=None):
        self.parent = parent
        self.callback = callback

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("400x250")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Dialog was closed via window close button
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_cancel)

        # Variables
        self.name_var = tk.StringVar(value=name)
        self.bs_instance_var = tk.StringVar(value=bluestacks_instance)
        self.adb_port_var = tk.StringVar(value=adb_port)
        self.description_var = tk.StringVar(value=description)

        # Create widgets
        self.create_widgets()

    def create_widgets(self):
        # Main frame
        frame = ttk.Frame(self.dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        # Form fields
        ttk.Label(frame, text="Instance Name:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.name_var, width=30).grid(row=0, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="BlueStacks Instance:").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.bs_instance_var, width=30).grid(row=1, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="ADB Port:").grid(row=2, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.adb_port_var, width=10).grid(row=2, column=1, sticky=tk.W, pady=5)

        ttk.Label(frame, text="Description:").grid(row=3, column=0, sticky=tk.W, pady=5)
        ttk.Entry(frame, textvariable=self.description_var, width=30).grid(row=3, column=1, sticky=tk.W, pady=5)

        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=4, column=0, columnspan=2, pady=10)

        ttk.Button(button_frame, text="Save", command=self.on_save).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.on_cancel).pack(side=tk.RIGHT, padx=5)

    def on_save(self):
        """Save changes and close dialog"""
        name = self.name_var.get().strip()
        bs_instance = self.bs_instance_var.get().strip()
        adb_port = self.adb_port_var.get().strip()
        description = self.description_var.get().strip()

        # Validate fields
        if not name:
            messagebox.showerror("Error", "Instance name cannot be empty")
            return

        if not bs_instance:
            messagebox.showerror("Error", "BlueStacks instance name cannot be empty")
            return

        if not adb_port:
            messagebox.showerror("Error", "ADB port cannot be empty")
            return

        # Call callback
        if self.callback:
            self.callback(name, bs_instance, adb_port, description)

        self.dialog.destroy()

    def on_cancel(self):
        """Cancel and close dialog"""
        self.dialog.destroy()


class InstanceNameDialog:
    """Simple dialog to get a new instance name"""

    def __init__(self, parent, title, default_name="", callback=None):
        self.parent = parent
        self.callback = callback

        # Create dialog window
        self.dialog = tk.Toplevel(parent)
        self.dialog.title(title)
        self.dialog.geometry("300x120")
        self.dialog.resizable(False, False)
        self.dialog.transient(parent)
        self.dialog.grab_set()

        # Dialog was closed via window close button
        self.dialog.protocol("WM_DELETE_WINDOW", self.on_cancel)

        # Variables
        self.name_var = tk.StringVar(value=default_name)

        # Create widgets
        self.create_widgets()

    def create_widgets(self):
        # Main frame
        frame = ttk.Frame(self.dialog, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        # Name field
        ttk.Label(frame, text="New Instance Name:").pack(anchor=tk.W, pady=5)
        name_entry = ttk.Entry(frame, textvariable=self.name_var, width=30)
        name_entry.pack(fill=tk.X, pady=5)
        name_entry.focus_set()  # Set focus to entry field

        # Buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=10)

        ttk.Button(button_frame, text="OK", command=self.on_ok).pack(side=tk.RIGHT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=self.on_cancel).pack(side=tk.RIGHT, padx=5)

    def on_ok(self):
        """Save name and close dialog"""
        name = self.name_var.get().strip()

        # Validate name
        if not name:
            messagebox.showerror("Error", "Instance name cannot be empty")
            return

        # Call callback
        if self.callback:
            self.callback(name)

        self.dialog.destroy()

    def on_cancel(self):
        """Cancel and close dialog"""
        self.dialog.destroy()


# Test function
if __name__ == "__main__":
    # Create a root window
    root = tk.Tk()
    root.title("Test Instance Manager")
    root.geometry("300x200")

    # Create instance manager
    instance_manager = InstanceManager()


    # Callback function
    def on_instance_selected(instance_id):
        print(f"Selected instance: {instance_id}")


    # Button to open dialog
    ttk.Button(
        root,
        text="Open Instance Manager",
        command=lambda: InstanceManagerDialog(root, instance_manager, on_instance_selected)
    ).pack(pady=20)

    root.mainloop()