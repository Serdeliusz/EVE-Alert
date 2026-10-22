from typing import TYPE_CHECKING

import customtkinter

if TYPE_CHECKING:
    from evealert.menu.main import MainMenu


class ConfigModeMenu:
    """Configuration mode menu for region selection.

    Provides a guide window with instructions for selecting the alert,
    faction and system name regions using keyboard hotkeys (F1/F2/F3). Manages the visual state of the
    config mode button to indicate when the system is in configuration mode.

    Attributes:
        main: Reference to MainMenu instance
        open: Whether the config window is currently open
        changed: Whether configuration has been modified
        alert_region: Whether alert region selection is active
        faction_region: Whether faction region selection is active
        system_region: Whether system name region selection is active
    """

    def __init__(self, main: "MainMenu") -> None:
        """Initialize the configuration mode menu.

        Args:
            main: Reference to the MainMenu instance
        """
        self.main = main
        self.open = False
        self.changed = False

        self.alert_region = False
        self.faction_region = False
        self.system_region = False

        self.description_window = customtkinter.CTkToplevel(self.main)
        self.description_window.title("Tryb konfiguracji")
        self.description_window.withdraw()

        description_text = "Obszar alarmu: naciśnij F1.\n"
        description_text += "Obszar frakcji: naciśnij F2.\n"
        description_text += "Obszar nazwy systemu: naciśnij F3.\n"
        description_text += (
            "\nPo naciśnięciu F1, F2 lub F3 zaznacz obszar myszą (przeciągnij).\n"
        )
        description_text += (
            "\nF3: zaznacz w grze nazwę systemu, w którym jesteś\n"
            "(panel lokalizacji w lewym górnym rogu, np. „Jita 1.0”).\n"
            "Gdy odczytana nazwa jest na liście systemów\n"
            "ignorowanych w Ustawieniach, alarmy o wrogach są pomijane.\n"
        )
        description_text += "\nAby przerwać, naciśnij ESC.\n"

        menu_frame = customtkinter.CTkFrame(self.description_window)
        menu_frame.pack(side="left", padx=20, pady=20)

        description_label = customtkinter.CTkLabel(
            menu_frame, text=description_text, justify="left"
        )
        description_label.pack(padx=20, pady=20)

        close_button = customtkinter.CTkButton(
            menu_frame, text="Zamknij", command=self.clean_up
        )
        close_button.pack(pady=10)

        self.description_window.protocol("WM_DELETE_WINDOW", self.clean_up)

    @property
    def is_open(self) -> bool:
        """Returns True if the description window is open."""
        return self.open

    @property
    def is_alert_region(self) -> bool:
        """Returns True if the alert region is active."""
        return self.alert_region

    @property
    def is_faction_region(self) -> bool:
        """Returns True if the faction region is active."""
        return self.faction_region

    @property
    def is_system_region(self) -> bool:
        """Returns True if the system name region selection is active."""
        return self.system_region

    @property
    def is_selecting(self) -> bool:
        """Returns True while any region selection is active."""
        return self.alert_region or self.faction_region or self.system_region

    @property
    def is_changed(self) -> bool:
        """Returns True if the configuration mode has been changed."""
        return self.changed

    def clean_up(self) -> None:
        """Close the configuration window and reset button color."""
        if self.is_open:
            self.open = False
            self.main.mainmenu_buttons.config_mode_menu.configure(
                fg_color="#1f538d", hover_color="#14375e"
            )
            # hide the description window
            self.description_window.withdraw()

    def open_menu(self) -> None:
        """Open or close the configuration mode guide window.

        Shows instructions for F1/F2/F3 region selection. Positions the window
        to the right of the main menu. Updates button color to indicate active state.
        """
        if not self.is_open:
            self.open = True
            self.main.mainmenu_buttons.config_mode_menu.configure(
                fg_color="#fa0202", hover_color="#bd291e"
            )

            # position the description window to the right of the main menu
            main_menu_x, main_menu_y = (
                self.main.winfo_x(),
                self.main.winfo_y(),
            )
            main_menu_width, _ = (
                self.main.winfo_width(),
                self.main.winfo_height(),
            )

            # Size the window to its content
            self.description_window.update_idletasks()
            description_window_width = max(
                435, self.description_window.winfo_reqwidth()
            )
            description_window_height = max(
                300, self.description_window.winfo_reqheight()
            )

            description_window_x = main_menu_x + main_menu_width + 10
            description_window_y = main_menu_y

            self.description_window.geometry(
                f"{description_window_width}x{description_window_height}+{description_window_x}+{description_window_y}"
            )

            # show the description window
            self.description_window.deiconify()
        else:
            self.clean_up()
