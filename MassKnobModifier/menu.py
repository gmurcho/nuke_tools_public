import nuke
import MassKnobModifier

# Add menu item
m = nuke.menu("Nuke")
my_menu = m.addMenu("g")
my_menu.addCommand( "Mass Knob Modifier","MassKnobModifier.mass_knob_modifier()", "ctrl+m")
