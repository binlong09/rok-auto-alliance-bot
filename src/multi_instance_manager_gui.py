#!/usr/bin/env python3
import os
import sys
import logging
import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time

from instance_manager import InstanceManager
from instance_manager_gui import InstanceManagerDialog
from multi_instance_launcher import MultiInstanceLauncher


class MultiInstanceManagerGUI:
    """GUI for managing and running multiple BlueStacks instances"""

    def __init__(self, root):
        self.root = root
        self.root.title("RoK Multi-Instance Manager")
        self.root.geometry("900x700")
        self.root.resizable(True, True)
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Setup logging
        self.setup_logging()

        # Initialize managers
        self.instance_manager = InstanceManager()
        self.launcher = MultiInstanceLauncher(self.instance_manager)

        # Set callbacks
        self.launcher.set_callbacks(
            log_callback=self.on_instance_log,
            status_callback=self.on_instance_status_update
        )

        # Track if app is closing
        self.is_closing = False

        # Auto exit option
        self.auto_exit_var = True

        # Create UI elements
        self.create_widgets()

        # Load instances
        self.load_instances()

        # Status update thread
        self.status_thread = threading.Thread(target=self.update_status_thread, daemon=True)
        self.status_thread.start()

    def setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(message)s",
            handlers=[
                logging.FileHandler("multi_instance.log"),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def create_widgets(self):
        """Create UI widgets"""
        # Main frame with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Top frame for instance management buttons
        top_frame = ttk.Frame(main_frame)
        top_frame.pack(fill=tk.X, pady=(0, 10))

        # Manager buttons
        ttk.Button(
            top_frame,
            text="Manage Instances",
            command=self.open_instance_manager
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            top_frame,
            text="Refresh List",
            command=self.load_instances
        ).pack(side=tk.LEFT, padx=5)

        ttk.Button(
            top_frame,
            text="Launch All",
            command=self.launch_all_instances
        ).pack(side=tk.RIGHT, padx=5)

        ttk.Button(
            top_frame,
            text="Stop All",
            command=self.stop_all_instances
        ).pack(side=tk.RIGHT, padx=5)

        # Auto-exit option
        self.auto_exit_var = tk.BooleanVar(value=True)
        auto_exit_cb = ttk.Checkbutton(
            top_frame,
            text="Auto-exit BlueStacks after completion",
            variable=self.auto_exit_var,
            command=self.toggle_auto_exit
        )
        auto_exit_cb.pack(side=tk.LEFT, padx=20)

        # Instances panel (left side)
        instances_frame = ttk.LabelFrame(main_frame, text="BlueStacks Instances")
        instances_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=False, padx=(0, 5))

        # Create Treeview for instances
        self.instances_tree = ttk.Treeview(
            instances_frame,
            columns=("name", "bs_instance", "status"),
            show="headings",
            selectmode="extended"  # This allows multiple selection with Shift/Ctrl keys
        )

        # Define columns
        self.instances_tree.heading("name", text="Name")
        self.instances_tree.heading("bs_instance", text="BlueStacks Instance")
        self.instances_tree.heading("status", text="Status")

        self.instances_tree.column("name", width=150)
        self.instances_tree.column("bs_instance", width=150)
        self.instances_tree.column("status", width=100)

        # Scrollbar for treeview
        scrollbar = ttk.Scrollbar(instances_frame, orient=tk.VERTICAL, command=self.instances_tree.yview)
        self.instances_tree.configure(yscrollcommand=scrollbar.set)

        # Pack treeview and scrollbar
        self.instances_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind selection event
        self.instances_tree.bind("<<TreeviewSelect>>", self.on_instance_select)

        # Create buttons under the treeview
        buttons_frame = ttk.Frame(instances_frame)
        buttons_frame.pack(fill=tk.X, pady=5)

        # 2. Add a "Launch Selected" button to the buttons_frame under the treeview:
        # Find the section with launch_button, stop_button, edit_button and add:
        self.launch_selected_button = ttk.Button(
            buttons_frame,
            text="Launch Selected",
            command=self.launch_selected_instances,
            state=tk.DISABLED
        )
        self.launch_selected_button.pack(side=tk.LEFT, padx=5)

        self.launch_button = ttk.Button(
            buttons_frame,
            text="Launch",
            command=self.launch_selected_instance,
            state=tk.DISABLED
        )
        self.launch_button.pack(side=tk.LEFT, padx=5)

        self.stop_button = ttk.Button(
            buttons_frame,
            text="Stop",
            command=self.stop_selected_instance,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)

        self.edit_button = ttk.Button(
            buttons_frame,
            text="Edit Config",
            command=self.edit_selected_instance,
            state=tk.DISABLED
        )
        self.edit_button.pack(side=tk.LEFT, padx=5)

        # Log panel (right side)
        log_frame = ttk.LabelFrame(main_frame, text="Instance Logs")
        log_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Instance info at top of log panel
        info_frame = ttk.Frame(log_frame)
        info_frame.pack(fill=tk.X, pady=5)

        ttk.Label(info_frame, text="Selected Instance:").pack(side=tk.LEFT, padx=5)

        self.selected_instance_label = ttk.Label(info_frame, text="None", font=("", 10, "bold"))
        self.selected_instance_label.pack(side=tk.LEFT, padx=5)

        ttk.Label(info_frame, text="Status:").pack(side=tk.LEFT, padx=(15, 5))

        self.selected_instance_status = ttk.Label(info_frame, text="Not Running")
        self.selected_instance_status.pack(side=tk.LEFT, padx=5)

        # Log text widget
        self.log_text = tk.Text(log_frame, wrap=tk.WORD, width=60)
        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Scrollbar for log text
        log_scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Status bar at bottom
        status_bar = ttk.Frame(self.root)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, pady=5)

        ttk.Label(status_bar, text="Running Instances:").pack(side=tk.LEFT, padx=5)
        self.running_count_label = ttk.Label(status_bar, text="0")
        self.running_count_label.pack(side=tk.LEFT, padx=5)


    def toggle_auto_exit(self):
        """Toggle auto-exit setting in launcher"""
        self.launcher.set_exit_after_complete(self.auto_exit_var.get())
        self.logger.info(f"Auto-exit BlueStacks after completion: {self.auto_exit_var.get()}")


    def load_instances(self):
        """Load instances into treeview"""
        # Clear existing items
        for item in self.instances_tree.get_children():
            self.instances_tree.delete(item)

        # Get all instances
        instances = self.instance_manager.get_all_instances()

        # Get running instances
        running_instances = self.launcher.get_running_instances()

        # Add to treeview
        for instance in instances:
            # Set status
            status = "Running" if instance["id"] in running_instances else "Not Running"

            values = (
                instance["name"],
                instance["bluestacks_instance"],
                status
            )

            self.instances_tree.insert("", tk.END, instance["id"], values=values)

        # Update running count
        self.running_count_label.config(text=str(len(running_instances)))

        self.logger.info(f"Loaded {len(instances)} instances, {len(running_instances)} running")

    def update_instance_status(self, instance_id, status):
        """Update the status of an instance in the treeview"""
        # Find the item with the given instance_id
        item_id = self.find_instance_item(instance_id)
        if not item_id:
            return

        # Get current values
        current_values = self.instances_tree.item(item_id, "values")
        if not current_values or len(current_values) < 3:
            return

        # Update status
        new_values = (current_values[0], current_values[1], status)
        self.instances_tree.item(item_id, values=new_values)

        # Update selected instance status if this is the selected instance
        selection = self.instances_tree.selection()
        if selection and selection[0] == item_id:
            self.selected_instance_status.config(text=status)

        # Update running count
        running_instances = self.launcher.get_running_instances()
        self.running_count_label.config(text=str(len(running_instances)))

    def launch_selected_instances(self):
        """Launch all selected instances without showing delay dialog"""
        # Get selected instance IDs
        selected_ids = self.instances_tree.selection()

        if not selected_ids:
            messagebox.showinfo("No Selection", "No instances selected for launch.")
            return

        # Filter out already running instances
        running_instances = self.launcher.get_running_instances()
        to_launch = [instance_id for instance_id in selected_ids if instance_id not in running_instances]

        if not to_launch:
            messagebox.showinfo("Already Running", "All selected instances are already running.")
            return

        # Get instance names for display
        instance_names = []
        for instance_id in to_launch:
            instance = self.instance_manager.get_instance(instance_id)
            if instance:
                instance_names.append(instance["name"])
            else:
                instance_names.append(f"Instance {instance_id}")

        # Confirm with user
        names_str = "\n".join(f"• {name}" for name in instance_names[:5])
        if len(instance_names) > 5:
            names_str += f"\n• ...and {len(instance_names) - 5} more"

        confirm = messagebox.askyesno(
            "Confirm Launch",
            f"Launch the following {len(to_launch)} instances?\n\n{names_str}"
        )

        if not confirm:
            return

        # Default delay between instances (could be made configurable in settings)
        delay_seconds = 5

        # Start the launch process with the default delay
        self._launch_multiple_instances(to_launch, delay_seconds)

    # 5. Add the method to handle the actual launching:
    def _launch_multiple_instances(self, instance_ids, delay_seconds):
        """Launch multiple instances with progress display"""
        if not instance_ids:
            return

        # Show progress window
        progress_window = tk.Toplevel(self.root)
        progress_window.title("Launching Instances")
        progress_window.geometry("400x250")
        progress_window.transient(self.root)
        progress_window.grab_set()

        ttk.Label(
            progress_window,
            text=f"Launching {len(instance_ids)} instances...",
            font=("", 12, "bold")
        ).pack(pady=10)

        # Add progress bar
        progress = ttk.Progressbar(progress_window, orient="horizontal", length=350, mode="determinate")
        progress.pack(pady=10, padx=10, fill=tk.X)
        progress["maximum"] = len(instance_ids)
        progress["value"] = 0

        # Status text
        status_var = tk.StringVar(value="Starting...")
        ttk.Label(progress_window, textvariable=status_var).pack(pady=5)

        # List of instances being launched
        launch_frame = ttk.Frame(progress_window)
        launch_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        launch_list = tk.Text(launch_frame, height=8, width=45)
        launch_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(launch_frame, orient=tk.VERTICAL, command=launch_list.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        launch_list.config(yscrollcommand=scrollbar.set)

        # Function to launch instances in the background
        def launch_with_progress():
            try:
                # Get instance names for nicer display
                instance_names = {}
                for instance_id in instance_ids:
                    instance = self.instance_manager.get_instance(instance_id)
                    if instance:
                        instance_names[instance_id] = instance["name"]
                    else:
                        instance_names[instance_id] = f"Instance {instance_id}"

                # Launch each instance with feedback
                for i, instance_id in enumerate(instance_ids):
                    instance_name = instance_names.get(instance_id, f"Instance {instance_id}")

                    # Update progress window
                    self.root.after_idle(lambda: status_var.set(f"Launching {instance_name}..."))
                    self.root.after_idle(lambda: launch_list.insert(tk.END, f"Launching {instance_name}...\n"))
                    self.root.after_idle(lambda: launch_list.see(tk.END))
                    self.root.after_idle(lambda: progress.config(value=i))

                    # Launch the instance
                    success = self.launcher.launch_instance(instance_id)

                    if success:
                        status_msg = f"Launched {instance_name} successfully."
                        self.root.after_idle(lambda id=instance_id: self.update_instance_status(id, "Starting"))
                    else:
                        status_msg = f"Failed to launch {instance_name}."

                    # Update status
                    self.root.after_idle(lambda msg=status_msg: launch_list.insert(tk.END, f"{msg}\n"))
                    self.root.after_idle(lambda: launch_list.see(tk.END))

                    # Wait for the specified delay (except after the last instance)
                    if i < len(instance_ids) - 1 and delay_seconds > 0:
                        for sec in range(delay_seconds, 0, -1):
                            if sec % 5 == 0 or sec <= 3:  # Show countdown at intervals
                                status_msg = f"Waiting {sec} seconds before next launch..."
                                self.root.after_idle(lambda msg=status_msg: status_var.set(msg))
                            time.sleep(1)

                # All instances launched
                self.root.after_idle(lambda: status_var.set("All launch commands sent."))
                self.root.after_idle(lambda: progress.config(value=len(instance_ids)))

                # Wait a moment before closing the progress window
                time.sleep(2)

                # Final update to UI
                self.root.after_idle(self.load_instances)

                # Show completion message and close progress window
                self.root.after_idle(lambda: messagebox.showinfo(
                    "Launch Complete",
                    f"Started {len(instance_ids)} instances."
                ))
                self.root.after_idle(progress_window.destroy)

            except Exception as e:
                # Handle any errors
                self.logger.error(f"Error in launch operation: {e}")
                self.root.after_idle(lambda: messagebox.showerror(
                    "Error",
                    f"An error occurred during launch: {str(e)}"
                ))

                # Close the progress window
                self.root.after_idle(progress_window.destroy)

        # Run the launching process in a separate thread
        threading.Thread(target=launch_with_progress, daemon=True).start()

    def find_instance_item(self, instance_id):
        """Find treeview item ID for an instance ID"""
        # Check if the item exists directly
        if self.instances_tree.exists(instance_id):
            return instance_id

        # Otherwise search through all items
        for item_id in self.instances_tree.get_children():
            if item_id == instance_id:
                return item_id

        return None

    def get_selected_instance_id(self):
        """Get the selected instance ID"""
        selection = self.instances_tree.selection()
        if not selection:
            return None

        return selection[0]

    def on_instance_select(self, event):
        """Handle instance selection"""
        selection = self.instances_tree.selection()

        if not selection:
            # Disable all buttons if nothing is selected
            self.launch_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.DISABLED)
            self.edit_button.config(state=tk.DISABLED)
            self.launch_selected_button.config(state=tk.DISABLED)
            self.selected_instance_label.config(text="None")
            self.selected_instance_status.config(text="Not Running")
            self.log_text.delete(1.0, tk.END)
            return

        # Get running instances
        running_instances = self.launcher.get_running_instances()

        # Handle multiple selection
        if len(selection) > 1:
            # Multiple instances selected
            self.selected_instance_label.config(text=f"{len(selection)} instances selected")
            self.selected_instance_status.config(text="Multiple")

            # Enable launch selected button if at least one instance is not running
            can_launch = any(item_id not in running_instances for item_id in selection)
            self.launch_selected_button.config(state=tk.NORMAL if can_launch else tk.DISABLED)

            # Disable single-instance buttons
            self.launch_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.DISABLED)
            self.edit_button.config(state=tk.DISABLED)

            # Show info about multiple selection
            self.log_text.delete(1.0, tk.END)
            self.log_text.insert(tk.END, f"Selected {len(selection)} instances:\n\n")

            for item_id in selection:
                instance = self.instance_manager.get_instance(item_id)
                if instance:
                    status = "Running" if item_id in running_instances else "Not Running"
                    self.log_text.insert(tk.END, f"• {instance['name']} ({status})\n")

            return

        # Single instance selected - original behavior
        instance_id = selection[0]

        # Get instance details
        instance = self.instance_manager.get_instance(instance_id)
        if not instance:
            return

        # Update UI with instance info
        self.selected_instance_label.config(text=instance["name"])

        # Update status based on whether instance is running
        is_running = self.launcher.is_instance_running(instance_id)
        status = "Running" if is_running else "Not Running"
        self.selected_instance_status.config(text=status)

        # Enable/disable buttons based on status
        self.launch_button.config(state=tk.DISABLED if is_running else tk.NORMAL)
        self.stop_button.config(state=tk.NORMAL if is_running else tk.DISABLED)
        self.edit_button.config(state=tk.DISABLED if is_running else tk.NORMAL)
        self.launch_selected_button.config(state=tk.DISABLED if is_running else tk.NORMAL)

        # Clear log and show status
        self.log_text.delete(1.0, tk.END)
        self.log_text.insert(tk.END, f"Selected instance: {instance['name']}\n")
        self.log_text.insert(tk.END, f"Status: {status}\n")
        self.log_text.insert(tk.END, f"BlueStacks instance: {instance['bluestacks_instance']}\n")
        self.log_text.insert(tk.END, f"ADB port: {instance['adb_port']}\n\n")

        # Add placeholder for logs
        if is_running:
            self.log_text.insert(tk.END, "--- Automation Logs ---\n")
        else:
            self.log_text.insert(tk.END, "Start automation to see logs here.\n")

    def on_instance_log(self, instance_id, message):
        """Handle log messages from automation threads"""
        # If this is the currently selected instance, add to log
        selection = self.get_selected_instance_id()
        if selection and selection == instance_id:
            self.log_text.insert(tk.END, f"{message}\n")
            self.log_text.see(tk.END)  # Scroll to end

    def on_instance_status_update(self, instance_id, status):
        """Handle status updates from automation threads"""
        # Update instance status in UI
        self.update_instance_status(instance_id, status)

        # If this is the selected instance, update status label
        selection = self.get_selected_instance_id()
        if selection and selection == instance_id:
            self.selected_instance_status.config(text=status)

            # Enable/disable buttons based on status
            is_running = self.launcher.is_instance_running(instance_id)
            self.launch_button.config(state=tk.DISABLED if is_running else tk.NORMAL)
            self.stop_button.config(state=tk.NORMAL if is_running else tk.DISABLED)
            self.edit_button.config(state=tk.DISABLED if is_running else tk.NORMAL)

    def open_instance_manager(self):
        """Open the instance manager dialog"""
        dialog = InstanceManagerDialog(self.root, self.instance_manager, self.on_instances_changed)
        self.root.wait_window(dialog.dialog)

    def on_instances_changed(self, instance_id):
        """Handle changes from instance manager"""
        # Reload the instances list
        self.load_instances()

        # Select the changed instance if provided
        if instance_id:
            item_id = self.find_instance_item(instance_id)
            if item_id:
                self.instances_tree.selection_set(item_id)
                self.on_instance_select(None)

    def launch_selected_instance(self):
        """Launch automation for the selected instance"""
        instance_id = self.get_selected_instance_id()
        if not instance_id:
            return

        # Check if already running
        if self.launcher.is_instance_running(instance_id):
            messagebox.showinfo("Already Running", "This instance is already running.")
            return

        # Launch the instance
        success = self.launcher.launch_instance(instance_id)

        if success:
            self.logger.info(f"Started automation for instance {instance_id}")
            self.update_instance_status(instance_id, "Starting")

            # Update button states
            self.launch_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.edit_button.config(state=tk.DISABLED)
        else:
            messagebox.showerror("Launch Failed", "Failed to start automation for this instance.")

    def stop_selected_instance(self):
        """Stop automation for the selected instance"""
        instance_id = self.get_selected_instance_id()
        if not instance_id:
            return

        # Check if running
        if not self.launcher.is_instance_running(instance_id):
            messagebox.showinfo("Not Running", "This instance is not running.")
            return

        # Stop the instance
        success = self.launcher.stop_instance(instance_id)

        if success:
            self.logger.info(f"Stopped automation for instance {instance_id}")
            self.update_instance_status(instance_id, "Stopping")

            # Update button states
            self.launch_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.edit_button.config(state=tk.NORMAL)
        else:
            messagebox.showerror("Stop Failed", "Failed to stop automation for this instance.")

    def edit_selected_instance(self):
        """Edit configuration for the selected instance"""
        instance_id = self.get_selected_instance_id()
        if not instance_id:
            return

        # Check if running
        if self.launcher.is_instance_running(instance_id):
            messagebox.showinfo("Instance Running", "Cannot edit configuration while instance is running.")
            return

        # Open BlueStacks Manager GUI for this instance
        from bluestacks_manager_gui import RiseOfKingdomsManagerGUI

        # Create a new top-level window
        edit_window = tk.Toplevel(self.root)
        edit_window.title(f"Edit Instance: {self.instance_manager.get_instance(instance_id)['name']}")

        # Set instance manager to use this instance
        self.instance_manager.set_current_instance(instance_id)

        # Create the manager UI
        app = RiseOfKingdomsManagerGUI(edit_window)

        # Wait for window to close
        self.root.wait_window(edit_window)

        # Refresh instances list
        self.load_instances()

    def launch_all_instances(self):
        """Launch all instances"""
        # Get all non-running instances
        instances = self.instance_manager.get_all_instances()
        running_instances = self.launcher.get_running_instances()

        instances_to_launch = []
        for instance in instances:
            if instance["id"] not in running_instances:
                instances_to_launch.append(instance)

        if not instances_to_launch:
            messagebox.showinfo("All Running", "All instances are already running.")
            return

        # Confirm with user
        result = messagebox.askyesno(
            "Launch All",
            f"Launch automation for {len(instances_to_launch)} instances?\n\n"
            "This will start multiple BlueStacks instances which may impact system performance."
        )

        if not result:
            return

        # Launch each instance with a slight delay to avoid ADB conflicts
        for instance in instances_to_launch:
            success = self.launcher.launch_instance(instance["id"])
            if success:
                self.update_instance_status(instance["id"], "Starting")
            time.sleep(2)  # Small delay between launches

        # Refresh the instances list
        self.load_instances()

    def stop_all_instances(self):
        """Stop all running instances"""
        running_instances = self.launcher.get_running_instances()

        if not running_instances:
            messagebox.showinfo("None Running", "No instances are currently running.")
            return

        # Confirm with user
        result = messagebox.askyesno(
            "Stop All",
            f"Stop automation for {len(running_instances)} running instances?"
        )

        if not result:
            return

        # Stop all instances
        self.launcher.stop_all_instances()

        # Update status for all stopped instances
        for instance_id in running_instances:
            self.update_instance_status(instance_id, "Stopping")

        # Refresh the instances list
        self.load_instances()

        # Update selected instance UI if needed
        self.on_instance_select(None)

    def update_status_thread(self):
        """Thread to periodically update instance statuses"""
        while not self.is_closing:
            try:
                # Refresh running count
                running_instances = self.launcher.get_running_instances()
                self.root.after(0, lambda: self.running_count_label.config(text=str(len(running_instances))))

                # Check if selected instance status has changed
                selected_id = self.get_selected_instance_id()
                if selected_id:
                    is_running = self.launcher.is_instance_running(selected_id)
                    status = "Running" if is_running else "Not Running"

                    # Only update UI from main thread
                    self.root.after(0, lambda s=status, r=is_running: (
                        self.selected_instance_status.config(text=s),
                        self.launch_button.config(state=tk.DISABLED if r else tk.NORMAL),
                        self.stop_button.config(state=tk.NORMAL if r else tk.DISABLED),
                        self.edit_button.config(state=tk.DISABLED if r else tk.NORMAL)
                    ))

                # Sleep for a short time
                time.sleep(1)

            except Exception as e:
                self.logger.error(f"Error in status update thread: {e}")
                time.sleep(5)  # Longer sleep on error

    def on_closing(self):
        """Handle window closing"""
        # Check if any instances are running
        running_instances = self.launcher.get_running_instances()

        if running_instances:
            result = messagebox.askyesno(
                "Confirm Exit",
                f"There are {len(running_instances)} instances running.\n"
                "Stop all running instances and exit?"
            )

            if not result:
                return  # Cancel exit

            # Stop all instances
            self.launcher.stop_all_instances()

            # Wait a moment for stop messages to be processed
            time.sleep(0.5)

        # Set closing flag for threads
        self.is_closing = True

        # Shutdown the launcher
        self.launcher.shutdown()

        # Close the window
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = MultiInstanceManagerGUI(root)
    root.mainloop()