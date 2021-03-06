import os

import pyspeckit
import matplotlib
import numpy as np
from astropy import units as u
from astropy import log

from glue.utils.qt import load_ui
from glue.external.qt.QtCore import Qt
from glue.external.qt import QtGui
from glue.external.six import iteritems
from glue.core.callback_property import add_callback

from glue.utils import nonpartial
from glue.viewers.common.qt.data_viewer import DataViewer
from glue.viewers.common.qt.mpl_widget import MplWidget
from glue.viewers.common.qt.toolbar import GlueToolbar
from glue.core.roi import RectangularROI, XRangeROI
from glue.viewers.common.qt.mouse_mode import (RectangleMode, HRangeMode,)
from glue.utils.qt.widget_properties import CurrentTabProperty, ButtonProperty, TextProperty

from .viewer_options import OptionsWidget


class PyspeckitViewer(DataViewer):

    LABEL = "Pyspeckit data viewer"

    mode = CurrentTabProperty('_control_panel.tab_mode')

    line_identify = ButtonProperty('_control_panel.radio_line_peak')
    line_select = ButtonProperty('_control_panel.radio_line_selection')

    cont_select = ButtonProperty('_control_panel.radio_cont_selection')
    cont_exclude = ButtonProperty('_control_panel.radio_cont_exclusion')

    log_line = TextProperty('_control_panel.text_line')
    log_cont = TextProperty('_control_panel.text_cont')

    def __init__(self, session, parent=None):
        super(PyspeckitViewer, self).__init__(session, parent=parent)

        self._mpl_widget = MplWidget()
        self._mpl_axes = self._mpl_widget.canvas.fig.add_subplot(1,1,1)

        self._control_panel = load_ui('control_panel.ui', None,
                                directory=os.path.dirname(__file__))

        self._line_mode = QtGui.QButtonGroup()
        self._line_mode.addButton(self._control_panel.radio_line_peak)
        self._line_mode.addButton(self._control_panel.radio_line_selection)

        self._line_mode.buttonClicked.connect(nonpartial(lambda: self.set_mode(init=True)))

        self._cont_mode = QtGui.QButtonGroup()
        self._cont_mode.addButton(self._control_panel.radio_cont_selection)
        self._cont_mode.addButton(self._control_panel.radio_cont_exclusion)

        self._cont_mode.buttonClicked.connect(nonpartial(lambda: self.set_mode(init=True)))

        self._options_widget = OptionsWidget(data_viewer=self)

        self._splitter = QtGui.QSplitter()
        self._splitter.setOrientation(Qt.Horizontal)
        self._splitter.addWidget(self._mpl_widget)
        self._splitter.addWidget(self._control_panel)

        self.setCentralWidget(self._splitter)

        self.toolbar = self.make_toolbar()

        # nonpartial = wrapper that says don't pass additional arguments
        self._control_panel.tab_mode.currentChanged.connect(nonpartial(lambda: self.set_mode(init=True)))
        #self._control_panel.button_line_identify.toggled.connect(nonpartial(self.set_click_mode))
        #self._control_panel.radio_button....toggled.connect(nonpartial(self.set_click_mode))
        self._control_panel.button_fit.clicked.connect(nonpartial(self.run_fitter))
        #self._control_panel.

        self.spectra = {}
        self.spectrum = None


    def set_mode(self, init=False):
        log.info("Setting mode with init={0}.  mode={1}".format(init, self.mode))
        # do not allow THIS to override "official" toolbar modes: we handle those correctly already
        overwriteable_modes = ('line_identify', 'line_select', 'cont_select', 'cont_exclude', '')
        #from astropy import log
        #log.setLevel('DEBUG')
        if self.mode == 'Fit Line':
            if init:
                log.info("Activating fitter")
                self.spectrum.plotter.activate_interactive_fitter()
                assert self.spectrum.plotter._active_gui is not None
            self.spectrum.specfit.debug = self.spectrum.specfit._debug = True
            if self.line_identify:
                if self.toolbar.mode in overwriteable_modes:
                    self.toolbar.mode = 'line_identify'
                log.info("Identify mode")
            elif self.line_select:
                if self.toolbar.mode in overwriteable_modes:
                    self.toolbar.mode = 'line_select'
                log.info("Select mode")
        elif self.mode == 'Fit Continuum':
            if init:
                log.info("Activating continuum fitter")
                self.spectrum.plotter.activate_interactive_baseline_fitter(reset_selection=True)
                assert self.spectrum.plotter._active_gui is not None
            self.spectrum.baseline.debug = self.spectrum.baseline._debug = True
            if self.cont_select:
                if self.toolbar.mode in overwriteable_modes:
                    self.toolbar.mode = 'cont_select'
                log.info("Select mode")
            elif self.cont_exclude:
                if self.toolbar.mode in overwriteable_modes:
                    self.toolbar.mode = 'cont_exclude'
                log.info("Exclude mode")

        else:
            raise NotImplementedError("Unknown mode: {0}".format(self.mode))

    #def set_click_mode(self):
    #    assert self.mode == 'Fit Line'
    #    self.click_mode = 'Peak/Width Identification'

    def run_fitter(self):
        if self.mode == 'Fit Line':
            self.spectrum.specfit.button3action(None)
            self.spectrum.plotter.refresh()
        elif self.mode == 'Fit Continuum':
            self.spectrum.baseline.button3action(None)
            self.spectrum.plotter.refresh()

    def click_manager(self, event):
        """
        Pass events to the appropriate pyspeckit actions
        """
        if self.toolbar.mode in ('line_identify', 'line_select', 'cont_select', 'cont_exclude'):
            log.info("Toolbar: mode={0}".format(self.toolbar.mode))
            if self.line_identify:
                self.spectrum.specfit.guesspeakwidth(event)
                self.spectrum.plotter.refresh()
            elif self.line_select and self.mode == 'Fit Line':
                self.spectrum.specfit.selectregion_interactive(event)
            elif self.cont_select:
                self.spectrum.baseline.selectregion_interactive(event)
            elif self.cont_exclude:
                self.spectrum.baseline.selectregion_interactive(event, mark_include=False)
            else:
                log.info("Not in line fitter mode, clicks do NOTHING.")
        else:
            log.info("Toolbar: mode={0}".format(self.toolbar.mode))


    def add_subset(self, subset):
        # a subset is a data object except it's not....
        self._options_widget.append(subset.data)
        self.set_new_data(subset.data, mask=subset.to_mask())

    def add_data(self, data):

        self._options_widget.append(data)

        # TODO: have a better way to query the unit in Glue Data objects

        # DO NOT use this hack IF pyspeckit version includes the fix that checks for 'number'
        #self._mpl_axes.figure.number = 1

        self.set_new_data(data)

        self.set_mode()

        return True

    def set_new_data(self, data, mask=None):

        log.info("Setting new data")
        if data.ndim == 3:
            x_comp_id = data.world_component_ids[0]
            xunit = data.coords.wcs.wcs.cunit[2]
            cubedata = data[self._options_widget.y_att[0]]
            log.info('cubedata shape: {0}'.format(cubedata.shape))
            if mask is not None:
                cubedata = np.ma.masked_array(cubedata, ~mask)
                meandata = cubedata.mean(axis=2).mean(axis=1)
            else:
                meandata = cubedata.mean(axis=(1,2))
            log.info('meandata shape: {0}'.format(meandata.shape))
            ydata = meandata
            xdata = data[x_comp_id][:,0,0]
            log.info("xdata shape: {0}".format(xdata.shape))
            xdata = u.Quantity(xdata, xunit)
        elif data.ndim == 2:
            raise ValueError("can't handle images")
        elif data.ndim == 1:
            x_comp_id = data.world_component_ids[0]
            y_comp_id = self._options_widget.y_att[0]
            xunit = data.coords.wcs.wcs.cunit[0]
            xdata = u.Quantity(data[x_comp_id], xunit)
            ydata = data[y_comp_id]
        else:
            raise ValueError("??!?!?!!?wtf?!?!?!")

        self._options_widget.x_att = x_comp_id.label
        log.info("Done averaging or loading 1d")

        sp = pyspeckit.Spectrum(data=ydata, xarr=xdata)
        sp.plotter(axis=self._mpl_axes, clear=False, color=data.style.color)
        sp.plotter.figure.canvas.manager.toolbar = self.toolbar
        sp.plotter.axis.figure.canvas.mpl_connect('button_press_event',
                                                  self.click_manager)
        self.spectra[data] = sp
        self.spectrum = sp

        #else:
        #    # TODO: have a better way to query the unit in Glue Data objects

        #    self.spectrum.data = ydata
        #    self.spectrum.xarr = pyspeckit.units.SpectroscopicAxis(xdata)

        #    self.spectrum.plotter(clear=True)


    def _mouse_modes(self):
        axes = self._mpl_axes

        def apply_mode(mode):

            if self.line_select or self.cont_select:
                assert self.spectrum.plotter._active_gui is not None, "No active GUI tool in pyspeckit"
                roi = mode.roi()
                log.info("ROI: {0}".format(roi))
                if isinstance(roi, RectangularROI):
                    x1 = roi.xmin
                    x2 = roi.xmax
                elif isinstance(roi, XRangeROI):
                    x1 = roi.min
                    x2 = roi.max
                if x1>x2:
                    x1,x2 = x2,x1
                
                self.spectrum.plotter._active_gui.selectregion(xmin=x1,
                                                               xmax=x2,
                                                               highlight=True)

        rect = RectangleMode(axes, roi_callback=apply_mode)
        xra = HRangeMode(axes, roi_callback=apply_mode)
        return [rect, xra,]

    def make_toolbar(self):
        toolbar = GlueToolbar(self._mpl_widget.canvas, self,
                              name='pyspeckit Plot')

        for mode in self._mouse_modes():
            toolbar.add_mode(mode)
            #add_callback(mode, 'enabled', nonpartial(self.set_mode))

        #for mode_result in toolbar. :
        #    mode_result.triggered.connect(nonpartial(self.set_mode))
        toolbar.actionTriggered.connect(nonpartial(self.set_mode))

        self.addToolBar(toolbar)
        return toolbar

    def options_widget(self):
        return self._options_widget
