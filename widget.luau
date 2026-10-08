--!nonstrict
-- Bar button: click to open the switcher.

barWidget.setGlyph("chart-donut")
barWidget.setTooltip(noctalia.tr("ui.tooltip"))

function onClick()
  noctalia.runAsync({ noctalia.pluginDir() .. "/easy_windows.py" })
end
