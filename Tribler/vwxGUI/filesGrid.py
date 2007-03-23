import os, sys, wx
from Tribler.vwxGUI.GuiUtility import GUIUtility
from Tribler.Dialogs.ContentFrontPanel import ImagePanel, DetailPanel, TorrentPanel
from Tribler.utilities import *
from traceback import print_exc

import wx, os, sys, math
import wx.xrc as xrc

DEBUG = True

class filesGrid(wx.Panel):
    """
    Panel with automatic backgroundimage control.
    """
    def __init__(self, *args):
        if len(args) == 0:
            pre = wx.PrePanel()
            # the Create step is done by XRC.
            self.PostCreate(pre)
            self.Bind(wx.EVT_WINDOW_CREATE, self.OnCreate)
        else:
            wx.Panel.__init__(self, args[0], args[1], args[2], args[3])
            self._PostInit()
        
    def OnCreate(self, event):
        self.Unbind(wx.EVT_WINDOW_CREATE)
        wx.CallAfter(self._PostInit)
        self.Show()
        event.Skip()
        return True
    

    def _PostInit(self):
        # Do all init here

        #self.SetSize((500,500))
        self.SetBackgroundColour(wx.BLACK)
        self.parent = None
        self.guiUtility = GUIUtility.getInstance()
        self.utility = self.guiUtility.utility
        self.cols = 2
        self.items = 0
        self.data = {}
        self.currentData = 0
        self.standardPager = None
        self.detailPanel = None
        self.addComponents()
        self.Show()
        #torrents = []
        #for word in 10*['Jelle', 'is', 'very', 'cool', 'jade', 'jade', 'weird', 'Katja']:
        #    torrents.append({'content_name':word})
        #self.setData(torrents)
        self.guiUtility.report(self)
        
    def addComponents(self):
        self.Show(False)
        #self.SetBackgroundColour(wx.BLUE)
        self.vSizer = wx.BoxSizer(wx.VERTICAL)
        
        self.staticGrid = StaticGridPanel(self, self.cols)
        self.vSizer.Add(self.staticGrid, 1, wx.ALL|wx.EXPAND, 0)
                
        self.SetSizer(self.vSizer);
        self.SetAutoLayout(1);
        self.Layout();
        self.Refresh(True)
        self.Update()
        #print "vSizer: %s, Panel: %s"% (self.vSizer.GetSize(), self.GetSize())

    def setData(self, dataList, resetPages = True):
        #print 'SetData by thread: %s' % threading.currentThread()
        self.data = dataList
        if resetPages:
            self.currentData = 0
            if self.getStandardPager():
                self.standardPager.currentPage = 0
        self.refreshPanels()
        
        
    def refreshPanels(self):
        "Refresh TorrentPanels with correct data and refresh pagerPanel"
        if self.getStandardPager():
            self.standardPager.refresh()
                
        if self.data == None:
            self.staticGrid.clearAllData()
        else:
            for i in range(0, self.items):
                dataIndex = i+ self.currentData
                if dataIndex < len(self.data):
                    self.staticGrid.setData(i, self.data[dataIndex])
                else:
                    self.staticGrid.setData(i, None)
        
        self.staticGrid.updateSelection()
    
    def gridResized(self, rows):
        self.items = self.cols * rows
        self.refreshPanels()
        
    def setPageNumber(self, page):
        if not self.data:
            return
        old = self.currentData
        if self.items * page < len(self.data) and page>=0:
            self.currentData = self.items*page
        if old != self.currentData:
            self.refreshPanels()
        
    def getStandardPager(self):
        if self.standardPager:
            return True
        self.standardPager = self.guiUtility.request('standardPager')
        return self.standardPager != None
            
       
 


class StaticGridPanel(wx.Panel):
    """
    A panel that shows subpanels with a static column count
    and a rowcount dependend on the size of the StaticGridPanel
    
    """
    def __init__(self, parent, cols):
        wx.Panel.__init__(self, parent, -1, size=wx.DefaultSize)
        #self.SetSize((500,500))
        
        self.parent = parent
        self.cols = cols
        self.currentRows = 0
        self.subPanelHeight = 100 # This will be update after first refresh
        self.detailPanel = None
        
        self.panels = []
        self.currentData = 0
        self.Bind(wx.EVT_SIZE, self.onResize)
        
        self.addComponents()
        self.Centre()
        self.Show()
        self.Layout();
        self.Refresh()
        #print "vSizer: %s, Panel: %s"% (self.vSizer.GetSize(), self.GetSize())
        
        
    def addComponents(self):
        self.Show(False)
        self.SetBackgroundColour(wx.WHITE)
        self.vSizer = wx.BoxSizer(wx.VERTICAL)
        self.calculateRows()
        self.SetSizer(self.vSizer);
        self.SetAutoLayout(1);
        

    def setData(self, panelNumber, data):
        try:
            hSizer = self.vSizer.GetItem(panelNumber%self.currentRows).GetSizer()
            panel = hSizer.GetItem(panelNumber/ self.currentRows).GetWindow()
            
            panel.setData(data)
        except:
            print >>sys.stderr,"contentpanel: Error: Could not set data in panel number %d, with %d cols" % (panelNumber, self.cols)
            print_exc(file=sys.stderr)
    
    def clearAllData(self):
        for i in range(0, self.items):
            self.setData(i, None)
            
    def onResize(self, event=None):
        
        #print ".",
        self.calculateRows()
        if event:
            event.Skip()
        
    def updateSubPanelHeight(self):
        try:
            self.subPanelHeight = self.vSizer.GetItem(0).GetSizer().GetItem(0).GetWindow().GetSize()[1]
        except:
            #print 'Could not get subpanelheight'
            pass
        
    def calculateRows(self):
    
        size = self.GetSize()
        oldRows = self.currentRows
        self.updateSubPanelHeight()
        if size[1] < 50 or self.subPanelHeight == 0:
            self.currentRows = 0
            self.items = 0
        else:
            self.currentRows = size[1] / self.subPanelHeight
            self.items = self.cols * self.currentRows
        
        if oldRows != self.currentRows: #changed
            if DEBUG:
                print >>sys.stderr,'contentpanel: Size updated to %d rows and %d columns, oldrows: %d'% (self.currentRows, self.cols, oldRows)
            
            self.updatePanel(oldRows, self.currentRows)
            self.parent.gridResized(self.currentRows)
            
    def updatePanel(self, oldRows, newRows):
        #
        if newRows > oldRows:
            for i in range(oldRows, newRows):
                hSizer = wx.BoxSizer(wx.HORIZONTAL)
                self.panels.append([])
                for panel in range(0, self.cols):
                    dataPanel = TorrentPanel(self)
                    #dataPanel = wx.Panel(self, wx.ID_ANY)
                    self.panels[i].append(dataPanel)
                    #dataPanel.SetSize((-1, self.subPanelHeight))
                    hSizer.Add(dataPanel, 1, wx.ALIGN_CENTER|wx.ALL|wx.GROW, 0)
                self.vSizer.Add(hSizer, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 0)
        elif newRows < oldRows:
            #print "Destroying row %d up to %d" % (newRows, oldRows-1)
            for row in range(oldRows-1, newRows-1, -1):
                # Destroy old panels
                for col in range(self.cols-1, -1, -1): #destroy panels right to left
                    panel = self.panels[row][col]
                    panel.Destroy()
                    del self.panels[row][col]
                    
                assert self.panels[row] == [], 'We deleted all panels, still the row is %s' % self.panels[row]
                del self.panels[row]
                self.vSizer.Detach(row) # detach hSizer of the row
          
    
    def updateSelection(self):
        """Deselect all torrentPanels, but the one selected in detailPanel
        If no torrent is selected in detailPanel, let first in grid be selected
        """
        if not self.hasDetailPanel():
            return
        
        
        title = None
        # Select first item
        if not self.detailPanel.data:
            try:
                firstItem = self.panels[0][0].data
                if firstItem:
                    self.detailPanel.setData(firstItem)
                    title = self.detailPanel.data.get('content_name')
            except:
                pass
        
        if self.detailPanel.data:
            title = self.detailPanel.data.get('content_name')

            
        
        for row in self.panels:
            for pan in row:
                try:
                    paneltitle = pan.data['content_name']
                except:
                    paneltitle = None
                    
                if paneltitle != title or paneltitle == None:
                    pan.deselect()
                else:
                    pan.select()
        
    def hasDetailPanel(self):
        if self.detailPanel:
            return True
        self.detailPanel = self.parent.guiUtility.request('standardDetails')
        return self.detailPanel != None
    
