#by Gautama Murcho.
#please e-mail gmurcho@gmail.com for any concerns or feedback!


import nuke
import nukescripts

KNOB_LABEL = "Common knobs"
VALUE_LABEL = "Value"

# Knobs you never want to see in the dropdown.
# If a knob doesn't exist on some nodes, only filter from the common set.
EXCLUDE_KNOBS = {
    "autolabel",
    "bookmark",
    "cached",
    "enable",
    "enable_mix_luminance",
    "help",
    "hide_input",
    "tile_color",
    "gl_color",
    "icon",
    "indicators",
    "inject",
    "Mask",
    "maskFrom",
    "maskFromFlag",
    "mix_luminance",
    "note_font_color",
    "onDestroy",
    "panel",
    "process_mask",
    "postage_stamp",
    "postage_stamp_frame",
    "useLifetime",
    "selected",
    "xpos",
    "ypos",
}


def _parse_value(value_str):
    """
    Parse a user-provided string into a Python value suitable for knob.setValue().
    Supports bools, ints/floats, comma-separated numeric lists, otherwise returns string.
    """
    if value_str is None:
        raise ValueError("Empty value.")

    v = str(value_str).strip()
    if v == "":
        raise ValueError("Empty value.")

    lower = v.lower()

    # Boolean support
    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False

    # Try int / float
    try:
        if "." in v or "e" in lower:
            return float(v)
        return int(v)
    except ValueError:
        pass

    # Try comma-separated values for multi-value knobs
    if "," in v:
        parts = [p.strip() for p in v.split(",")]
        parsed = []
        for p in parts:
            try:
                parsed.append(float(p) if ("." in p or "e" in p.lower()) else int(p))
            except ValueError:
                # Non-numeric lists: keep as strings
                return parts
        return parsed

    # Fallback to string (works for enums, labels, file paths, etc.)
    return v


def _set_knob_value_or_expression(knob, raw_value_str):
    """
    If raw_value_str starts with '=', set an expression (without the '=').
    Otherwise, set a parsed value normally.
    Returns "expression" or "value" for reporting.
    """
    if raw_value_str is None:
        raise ValueError("Empty value.")

    s = str(raw_value_str).strip()
    if s == "":
        raise ValueError("Empty value.")

    # Expression mode (prefix '=')
    if s.startswith("="):
        expr = s[1:].strip()
        if expr == "":
            raise ValueError("Empty expression.")

        # Try to set for all components if this is an array knob
        try:
            n = knob.arraySize()
        except Exception:
            n = 1

        if n and n > 1:
            for i in range(n):
                try:
                    knob.setExpression(expr, i)
                except TypeError:
                    knob.setExpression(expr)
                    break
        else:
            knob.setExpression(expr)

        return "expression"

    # Normal value mode
    parsed = _parse_value(s)

    if isinstance(parsed, list):
        # Multi-value knob support
        for i, val in enumerate(parsed):
            try:
                knob.setValue(val, i)
            except TypeError:
                knob.setValue(parsed)
                break
    else:
        knob.setValue(parsed)

    return "value"


class MassKnobModifierPanel(nukescripts.PythonPanel):
    """
    PythonPanel gives us proper static text via Text_Knob.
    """
    def __init__(self, knob_items):
        super(MassKnobModifierPanel, self).__init__("Mass Knob Modifier")

        self.knob_enum = nuke.Enumeration_Knob("common_knobs", KNOB_LABEL, knob_items)
        self.value_knob = nuke.String_Knob("value", VALUE_LABEL, "")

        self.tip = nuke.Text_Knob(
            "tip",
            "",
            "<br><span style='color:#808080;'>"
            "*for <b>expressions</b>, add a <b>=</b> before the expression.<br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ex: <b>=</b>$gui, <b>=</b>parent, etc."
            "<br></span>"
        )

        self.addKnob(self.knob_enum)
        self.addKnob(self.value_knob)
        self.addKnob(self.tip)

    def knobName(self):
        return self.knob_enum.value()

    def valueString(self):
        return self.value_knob.value()


def mass_knob_modifier():
    nodes = nuke.selectedNodes()
    if not nodes:
        nuke.message("No nodes selected.")
        return

    # --- Find common knobs across all selected nodes ---
    common = set(nodes[0].knobs().keys())
    for node in nodes[1:]:
        common &= set(node.knobs().keys())

    if not common:
        nuke.message("No common knobs found.")
        return

    # Remove excluded knobs (safe even if they weren't present)
    common -= EXCLUDE_KNOBS

    # --- Filter to meaningful knobs ---
    visible_common = []
    for k in common:
        knob = nodes[0].knob(k)
        if not knob:
            continue

        # Skip internal/script knobs
        if k in ("knobChanged", "onCreate", "updateUI"):
            continue

        # Skip non-editable or hidden knobs
        # (wrap in try for extra safety across Nuke versions / knob types)
        try:
            if not knob.visible() or not knob.enabled():
                continue
        except Exception:
            pass

        # Skip tabs, text labels, and script buttons (keeps list clean)
        if isinstance(knob, (nuke.Tab_Knob, nuke.Text_Knob, nuke.PyScript_Knob)):
            continue

        visible_common.append(k)

    visible_common = sorted(set(visible_common))

    if not visible_common:
        nuke.message("No usable common knobs found.")
        return

    # --- Build UI with PythonPanel ---
    panel = MassKnobModifierPanel(visible_common)
    if not panel.showModalDialog():
        return

    knob_name = panel.knobName()
    value_str = panel.valueString()

    if knob_name is None or str(knob_name).strip() == "":
        nuke.message("Please choose a knob.")
        return

    if value_str is None or str(value_str).strip() == "":
        nuke.message("Value cannot be empty.")
        return

    # --- Apply Changes ---
    changed = 0
    errors = []
    mode_used = None

    nuke.Undo().begin("Mass Knob Modifier")
    try:
        for node in nodes:
            knob = node.knob(knob_name)
            if not knob:
                continue

            try:
                mode_used = _set_knob_value_or_expression(knob, value_str)
                changed += 1
            except Exception as e:
                errors.append(f"{node.name()}: {e}")
    finally:
        nuke.Undo().end()

    # --- Report ---
    shown_value = str(value_str).strip()
    if shown_value.startswith("="):
        shown_value = shown_value[1:].strip()

    if mode_used == "expression":
        msg = f"Changed '{knob_name}' expression to {shown_value} on {changed} nodes."
    else:
        msg = f"Changed '{knob_name}' to {shown_value} on {changed} nodes."

    if errors:
        msg += f"\nErrors: {len(errors)}"
        msg += "\n" + "\n".join(errors[:10])
        if len(errors) > 10:
            msg += "\n..."

    nuke.message(msg)


mass_knob_modifier()
