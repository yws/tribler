# Written by Bram Cohen
# see LICENSE.txt for license information

from cStringIO import StringIO
from binascii import b2a_hex
from socket import error as socketerror
from urllib import quote
from struct import unpack
from sha import sha
from time import time
from binascii import b2a_hex
from __init__ import *

try:
    True
except:
    True = 1
    False = 0

DEBUG = True

MAX_INCOMPLETE = 8

protocol_name = 'BitTorrent protocol'
# Enable I-Share extensions:
# Left-most bit = Azureus Enhanced Messaging Protocol (AEMP)
# Left+42 bit = Tribler Overlay swarm extension
# Left+43 bit = Tribler Simple Merkle Hashes extension
# Right-most bit = BitTorrent DHT extension
#option_pattern = chr(0)*8
option_pattern = '\x00\x00\x00\x00\x00\x30\x00\x00' 

def toint(s):
    return long(b2a_hex(s), 16)

def make_readable(s):
    if not s:
        return ''
    if quote(s).find('%') >= 0:
        return b2a_hex(s).upper()
    return '"'+s+'"'


class IncompleteCounter:
    def __init__(self):
        self.c = 0
    def increment(self):
        self.c += 1
    def decrement(self):
        self.c -= 1
    def toomany(self):
        return self.c >= MAX_INCOMPLETE
    
incompletecounter = IncompleteCounter()


# header, reserved, download id, my id, [length, message]

class Connection:    # OverlaySocket, a better name for it?
    def __init__(self, Encoder, connection, id, ext_handshake = False, dns = None):
        self.Encoder = Encoder
        self.connection = connection    # SocketHandler.SingleSocket
        self.connecter_conn = None      # OverlayConnecter.Connection
        self.connecter = Encoder.connecter
        self.id = id
        self.dns = dns
        self.readable_id = make_readable(id)
        self.locally_initiated = (id != None)
        self.complete = False
        self.keepalive = lambda: None
        self.closed = False
        self.buffer = StringIO()
        self.overlay_version = CurrentVersion
        if self.locally_initiated:
            incompletecounter.increment()
        if self.locally_initiated or ext_handshake:
            self.connection.write(chr(len(protocol_name)) + protocol_name + 
                option_pattern + self.Encoder.download_id)
        if ext_handshake:
            self.Encoder.connecter.external_connection_made += 1
            self.connection.write(self.Encoder.my_id)
            self.next_len, self.next_func = 20, self.read_peer_id
        else:
            self.next_len, self.next_func = 1, self.read_header_len
        #TODO: auto close management
        #self.Encoder.raw_server.add_task(self._auto_close, 15)

    def get_ip(self, real=False):
        return self.connection.get_ip(real)

    def get_port(self, real=False):
        return self.connection.get_port(real)

    def get_myip(self, real=False):
        return self.connection.get_myip(real)

    def get_myport(self, real=False):
        return self.connection.get_myport(real)

    def get_id(self):
        return self.id

    def get_readable_id(self):
        return self.readable_id

    def is_locally_initiated(self):
        return self.locally_initiated

    def is_flushed(self):
        return self.connection.is_flushed()

    def set_options(self, s):
        pass    # used by future
                
    def read_header_len(self, s):
        if ord(s) != len(protocol_name):
            return None
        return len(protocol_name), self.read_header

    def read_header(self, s):
        if s != protocol_name:
            return None
        return 8, self.read_reserved

    def read_reserved(self, s):
        if DEBUG:
            print "olencoder: Reserved bits:", `s`
        self.set_options(s)
        return 20, self.read_download_id

    def read_download_id(self, s):
        if s != self.Encoder.download_id:
            return None
        if not self.locally_initiated:
            self.Encoder.connecter.external_connection_made += 1
            self.connection.write(chr(len(protocol_name)) + protocol_name + 
                option_pattern + self.Encoder.download_id + self.Encoder.my_id)
        return 20, self.read_peer_id

    def read_peer_id(self, s):
        if not self.id:
            self.id = s
            self.readable_id = make_readable(s)
        else:
            if s != self.id:
                return None
        self.complete = self.Encoder.got_id(self)
        if not self.complete:
            return None
        if not self.version_supported(s[16:18], s[18:20]):    # versioning protocol
            return None
        if self.locally_initiated:
            self.connection.write(self.Encoder.my_id)
            incompletecounter.decrement()
        c = self.Encoder.connecter.connection_made(self, self.dns)
        self.keepalive = c.send_keepalive
        self.connecter_conn = c
        def notify(connection=c):
            self.Encoder.overlayswarm.connectionMade(connection)
        self.Encoder.raw_server.add_task(notify, 0)
        return 4, self.read_len
    
    def version_supported(self, low_ver_str, cur_ver_str):
        """ overlay swarm versioning solution: use last 4 bytes in PeerID """
        
        low_ver = unpack('H', low_ver_str)[0]
        cur_ver = unpack('H', cur_ver_str)[0]
        if cur_ver != CurrentVersion:
            if low_ver > CurrentVersion:    # the other's version is too high
                return False
            if cur_ver < LowestVersion:     # the other's version is too low
                return False           
            if cur_ver < CurrentVersion and \
               cur_ver not in SupportedVersions:   # the other's version is not supported
                return False
            if cur_ver < CurretVersion:     # set low version as our version
                self.overlay_version = cur_ver
        return True

    def read_len(self, s):
        l = toint(s)
        if l > self.Encoder.max_len:
            return None
        return l, self.read_message

    def read_message(self, s):
        if s != '':
            self.connecter.got_message(self, s)
        return 4, self.read_len

    def read_dead(self, s):
        return None

    def _auto_close(self):
        if not self.complete:
            self.close()

    def close(self):
        if not self.closed:
            self.connection.close()
            self.sever()

    def sever(self):
        self.closed = True
        if self.Encoder.connections.has_key(self.connection):
            del self.Encoder.connections[self.connection]

        if self.complete:
            self.connecter.connection_lost(self)
        elif self.locally_initiated:
            incompletecounter.decrement()
        if self.connecter_conn:
            self.Encoder.overlayswarm.connectionLost(self.connecter_conn)

    def send_message_raw(self, message):
        if not self.closed:
            self.connection.write(message)

    def data_came_in(self, connection, s):
        self.Encoder.measurefunc(len(s))
        while 1:
            if self.closed:
                return
            i = self.next_len - self.buffer.tell()
            if i > len(s):
                self.buffer.write(s)
                return
            self.buffer.write(s[:i])
            s = s[i:]
            m = self.buffer.getvalue()
            self.buffer.reset()
            self.buffer.truncate()
            try:
                x = self.next_func(m)
            except:
                self.next_len, self.next_func = 1, self.read_dead
                raise
            if x is None:
                self.close()
                return
            self.next_len, self.next_func = x

    def connection_lost(self, connection):
        if DEBUG:
            print "olencoder: connection_lost"
        if self.Encoder.connections.has_key(connection):
            self.sever()

    def connection_flushed(self, connection):
        if self.complete:
            self.connecter.connection_flushed(self)
            
            
class OverlayEncoder:
    def __init__(self, overlayswarm, connecter, raw_server, my_id, max_len, 
            schedulefunc, keepalive_delay, download_id, 
            measurefunc, config):
        self.overlayswarm = overlayswarm
        self.connecter = connecter
        self.raw_server = raw_server
        self.my_id = my_id
        self.max_len = max_len
        self.schedulefunc = schedulefunc
        self.keepalive_delay = keepalive_delay
        self.download_id = download_id
        self.measurefunc = measurefunc
        self.config = config
        self.connections = {}
        self.banned = {}
        self.to_connect = []
        self.paused = False
        if self.config['max_connections'] == 0:
            self.max_connections = 2 ** 30
        else:
            self.max_connections = self.config['max_connections']
        # overlay swarm doesn't send keeplive if not necessary 
        #schedulefunc(self.send_keepalives, keepalive_delay)     

    def send_keepalives(self):
        if self.paused:
            return
        for c in self.connections.values():
            c.keepalive()

    def keep_alive(self):
        self.send_keepalives()
        self.schedulefunc(self.keep_alive, self.keepalive_delay)

    def start_connections(self, list):
        if not self.to_connect:
            self.raw_server.add_task(self._start_connection_from_queue)
        self.to_connect = list

    def _start_connection_from_queue(self):
        if self.connecter.external_connection_made:
            max_initiate = self.config['max_initiate']
        else:
            max_initiate = int(self.config['max_initiate']*1.5)
        cons = len(self.connections)
        if cons >= self.max_connections or cons >= max_initiate:
            delay = 60
        elif self.paused or incompletecounter.toomany():
            delay = 1
        else:
            delay = 0
            dns, id = self.to_connect.pop(0)
            self.start_connection(dns, id)
        if self.to_connect:
            self.raw_server.add_task(self._start_connection_from_queue, delay)

    def start_connection(self, dns, id):
        if (self.paused
             or len(self.connections) >= self.max_connections
             or id == self.my_id
             or self.banned.has_key(dns[0])):
            return True
        for v in self.connections.values():    # avoid duplicated connectiion from a single ip
            if v is None:
                continue
            if id and v.id == id:
                return True
            ip = v.get_ip(True)
            if ip != 'unknown' and ip == dns[0]:    # forbid to setup multiple connection on overlay swarm
                if DEBUG:
                    print "olencoder: Using existing connection to",dns
                return True
        try:
            if DEBUG:
                print "olencoder: Setting up new connection to",dns
            c = self.raw_server.start_connection(dns)
            con = Connection(self, c, id, dns = dns)
            self.connections[c] = con
            c.set_handler(con)
        except socketerror:
            return False
        return True

    def _start_connection(self, dns, id):
        def foo(self=self, dns=dns, id=id):
            self.start_connection(dns, id)
       
        self.schedulefunc(foo, 0)

    def got_id(self, connection):
        if connection.id == self.my_id:
            self.connecter.external_connection_made -= 1
            return False
        ip = connection.get_ip(True)
        if self.config['security'] and self.banned.has_key(ip):
            return False
        for v in self.connections.values():
            if connection is not v:
                if connection.id == v.id:
                    return False
                if self.config['security'] and ip != 'unknown' and ip == v.get_ip(True):
                    v.close()
        return True

    def external_connection_made(self, connection):
        """ Remotely initiated connection """

        if self.paused or len(self.connections) >= self.max_connections:
            connection.close()
            return False
        con = Connection(self, connection, None)
        self.connections[connection] = con
        connection.set_handler(con)
        return True

    def externally_handshaked_connection_made(self, connection, options, already_read):
        if self.paused or len(self.connections) >= self.max_connections:
            connection.close()
            return False
        con = Connection(self, connection, None, True)
        self.connections[connection] = con
        connection.set_handler(con)
        if already_read:
            con.data_came_in(con, already_read)
        return True

    def close_all(self):
        for c in self.connections.values():
            c.close()
        self.connections = {}

    def ban(self, ip):
        self.banned[ip] = 1

    def pause(self, flag):
        self.paused = flag
