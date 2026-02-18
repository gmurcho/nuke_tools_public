# by Gautama Murcho.
# please e-mail gmurcho@gmail.com for any concerns or feedback!

import nuke
import nukescripts

KNOB_LABEL = "Common knobs"
VALUE_LABEL = "Value"
CLASS_LABEL = "Class"

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
    if value_str is None:
        raise ValueError("Empty value.")
    v = str(value_str).strip()
    if v == "":
        raise ValueError("Empty value.")

    lower = v.lower()

    if lower in ("true", "yes", "on"):
        return True
    if lower in ("false", "no", "off"):
        return False

    try:
        if "." in v or "e" in lower:
            return float(v)
        return int(v)
    except ValueError:
        pass

    if "," in v:
        parts = [p.strip() for p in v.split(",")]
        parsed = []
        for p in parts:
            try:
                parsed.append(float(p) if ("." in p or "e" in p.lower()) else int(p))
            except ValueError:
                return parts
        return parsed

    return v


def _coerce_for_knob(knob, parsed):
    """
    Coerce a parsed value to what this specific knob expects.

    Fixes cases like Read 'frame' when in expression mode:
      - knob is effectively string-backed, so setValue(1) errors
      - but setValue("1") is valid
    Also helps enumeration knobs:
      - allow user to type 'hold' or 'start at' instead of an index.
    """
    # 1) String knobs must receive strings
    try:
        if isinstance(knob, nuke.String_Knob):
            if isinstance(parsed, list):
                return ", ".join(str(x) for x in parsed)
            return str(parsed)
    except Exception:
        pass

    # 2) Enumeration knobs: allow label input (e.g. "hold", "start at")
    try:
        if isinstance(knob, nuke.Enumeration_Knob) and isinstance(parsed, str):
            opts = list(knob.values())

            # exact match
            if parsed in opts:
                return opts.index(parsed)

            # case-insensitive match
            low = parsed.lower()
            for i, o in enumerate(opts):
                if str(o).lower() == low:
                    return i
    except Exception:
        pass

    return parsed


def _set_knob_value_or_expression(knob, raw_value_str):
    if raw_value_str is None:
        raise ValueError("Empty value.")
    s = str(raw_value_str).strip()
    if s == "":
        raise ValueError("Empty value.")

    # Expressions: user types "=<expr>"
    if s.startswith("="):
        expr = s[1:].strip()
        if expr == "":
            raise ValueError("Empty expression.")

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

    # Normal values
    parsed = _parse_value(s)
    parsed = _coerce_for_knob(knob, parsed)

    # Special behavior for label knob: append instead of overwrite
    try:
        if knob.name() == "label" and not s.startswith("="):
            existing = knob.value()
            new_text = str(parsed)

            if existing and existing.strip():
                parsed = existing.rstrip() + "\n" + new_text
            else:
                parsed = new_text
    except Exception:
        pass

    if isinstance(parsed, list):
        for i, val in enumerate(parsed):
            try:
                knob.setValue(val, i)
            except TypeError:
                knob.setValue(parsed)
                break
    else:
        knob.setValue(parsed)

    return "value"


def _all_nodes_root(recurse_groups=True):
    root = nuke.root()
    root.begin()
    try:
        return nuke.allNodes(recurseGroups=recurse_groups)
    finally:
        root.end()


def _nodes_by_class(class_name):
    if class_name is None:
        return []
    target = str(class_name).strip()
    if not target:
        return []

    all_nodes = _all_nodes_root(recurse_groups=True)

    exact = [n for n in all_nodes if n.Class() == target]
    if exact:
        return exact

    t_low = target.lower()
    return [n for n in all_nodes if n.Class().lower() == t_low]


def _common_knobs_for_nodes(nodes):
    if not nodes:
        return []

    common = set(nodes[0].knobs().keys())
    for node in nodes[1:]:
        common &= set(node.knobs().keys())

    if not common:
        return []

    common -= EXCLUDE_KNOBS

    visible_common = []
    for k in common:
        knob = nodes[0].knob(k)
        if not knob:
            continue

        if k in ("knobChanged", "onCreate", "updateUI"):
            continue

        try:
            if not knob.visible() or not knob.enabled():
                continue
        except Exception:
            pass

        if isinstance(knob, (nuke.Tab_Knob, nuke.Text_Knob, nuke.PyScript_Knob)):
            continue

        visible_common.append(k)

    return sorted(set(visible_common))


def _selected_node_class():
    sel = nuke.selectedNodes()
    if not sel:
        return None
    return sel[0].Class()


class MassKnobModifierPanel(nukescripts.PythonPanel):
    """
    Modes:
      - by selection
      - by class
      - by class from selection
    """
    def __init__(self, knob_items):
        super(MassKnobModifierPanel, self).__init__("Mass Knob Modifier")

        # Grey "mode" label in front of dropdown (label column)
        self.mode = nuke.Enumeration_Knob(
            "mode",
            "<span style='color:#808080;'>mode</span>",
            ["by selection", "by class", "by class from selection"]
        )

        self.class_name = nuke.String_Knob("class_name", CLASS_LABEL, "")
        self.update_btn = nuke.PyScript_Knob("update_knobs", "Update knobs")

        self.divider = nuke.Text_Knob(
            "divider",
            "",
            "<span style='color:#3a3a3a;'>"
            "────────────────────────────────────────"
            "</span>"
        )

        self.knob_enum = nuke.Enumeration_Knob(
            "common_knobs", KNOB_LABEL, knob_items if knob_items else [""]
        )
        self.value_knob = nuke.String_Knob("value", VALUE_LABEL, "")

        self.tip = nuke.Text_Knob(
            "tip",
            "",
            "<br><span style='color:#808080;'>"
            "*for <b>expressions</b>, add a <b>=</b> before the expression.<br>"
            "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;ex: <b>=</b>$gui, <b>=</b>parent, etc."
            "<br></span>"
        )

        self.addKnob(self.mode)
        self.addKnob(self.class_name)
        self.addKnob(self.update_btn)
        self.addKnob(self.divider)
        self.addKnob(self.knob_enum)
        self.addKnob(self.value_knob)
        self.addKnob(self.tip)

        self._apply_mode_visibility()

    def _apply_mode_visibility(self):
        m = self.mode.value()
        if m == "by selection":
            self.class_name.setVisible(False)
            self.update_btn.setVisible(False)
        elif m == "by class":
            self.class_name.setVisible(True)
            self.update_btn.setVisible(True)
        else:  # by class from selection
            self.class_name.setVisible(False)
            self.update_btn.setVisible(True)

    def knobChanged(self, k):
        if k is self.mode:
            self._apply_mode_visibility()

        if k is self.update_btn:
            self._refresh_knob_dropdown_for_mode()

    def _refresh_knob_dropdown_for_mode(self):
        m = self.mode.value()

        if m == "by class":
            class_name = self.class_name.value()
            targets = _nodes_by_class(class_name)
            if not targets:
                nuke.message(
                    f"No nodes found with class '{class_name}'.\n"
                    f"Examples: Merge2, Blur, Grade"
                )
                return

        elif m == "by class from selection":
            class_name = _selected_node_class()
            if not class_name:
                nuke.message("Select a node first (to choose the class).")
                return

            targets = _nodes_by_class(class_name)
            if not targets:
                nuke.message(f"No nodes found with class '{class_name}'.")
                return

        else:
            return

        knob_items = _common_knobs_for_nodes(targets)
        if not knob_items:
            nuke.message(f"No usable common knobs found for class '{targets[0].Class()}'.")
            return

        current = self.knob_enum.value()
        self.knob_enum.setValues(knob_items)
        self.knob_enum.setValue(current if current in knob_items else knob_items[0])

    def modeValue(self):
        return self.mode.value()

    def classValue(self):
        return self.class_name.value()

    def knobName(self):
        return self.knob_enum.value()

    def valueString(self):
        return self.value_knob.value()


def mass_knob_modifier():
    selected = nuke.selectedNodes()
    initial_knobs = _common_knobs_for_nodes(selected) if selected else []

    panel = MassKnobModifierPanel(initial_knobs)
    if not panel.showModalDialog():
        return

    mode = panel.modeValue()
    value_str = panel.valueString()
    knob_name = panel.knobName()

    if value_str is None or str(value_str).strip() == "":
        nuke.message("Value cannot be empty.")
        return

    target_class = None

    if mode == "by class":
        target_class = panel.classValue()
        targets = _nodes_by_class(target_class)
        if not targets:
            nuke.message(f"No nodes found with class '{target_class}'.\nExamples: Merge2, Blur, Grade")
            return
        target_class = targets[0].Class()

    elif mode == "by class from selection":
        target_class = _selected_node_class()
        if not target_class:
            nuke.message("Select a node first (to choose the class).")
            return

        targets = _nodes_by_class(target_class)
        if not targets:
            nuke.message(f"No nodes found with class '{target_class}'.")
            return
        target_class = targets[0].Class()

    else:
        targets = nuke.selectedNodes()
        if not targets:
            nuke.message("No nodes selected.")
            return

    knob_items = _common_knobs_for_nodes(targets)
    if not knob_items:
        nuke.message("No usable common knobs found.")
        return

    if knob_name not in knob_items:
        knob_name = knob_items[0]

    changed = 0
    errors = []
    mode_used = None

    nuke.Undo().begin("Mass Knob Modifier")
    try:
        for node in targets:
            k = node.knob(knob_name)
            if not k:
                continue
            try:
                mode_used = _set_knob_value_or_expression(k, value_str)
                changed += 1
            except Exception as e:
                errors.append(f"{node.name()}: {e}")
    finally:
        nuke.Undo().end()

    shown_value = str(value_str).strip()
    if shown_value.startswith("="):
        shown_value = shown_value[1:].strip()

    if mode_used == "expression":
        if target_class:
            msg = f"Changed '{knob_name}' expression to {shown_value} on all {changed} {target_class} nodes."
        else:
            msg = f"Changed '{knob_name}' expression to {shown_value} on {changed} nodes."
    else:
        if target_class:
            msg = f"Changed '{knob_name}' to {shown_value} on all {changed} {target_class} nodes."
        else:
            msg = f"Changed '{knob_name}' to {shown_value} on {changed} nodes."

    if errors:
        msg += f"\nErrors: {len(errors)}"
        msg += "\n" + "\n".join(errors[:10])
        if len(errors) > 10:
            msg += "\n..."

    nuke.message(msg)


# Don't auto-run on import if this lives in menu.py / startup:
#mass_knob_modifier()
