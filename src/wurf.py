#!/usr/bin/env python3
#  wurf -- an ad-hoc single file webserver


from __future__ import annotations

from typing import Generator, BinaryIO

import sys, os, errno, socket, getopt, subprocess, tempfile
import urllib.request, urllib.parse, http.server
import email.parser
import readline
import configparser
import shutil, tarfile, zipfile
import struct
from io import BytesIO, StringIO
import ssl

maxdownloads = 1
cpid = -1
compressed = "gz"
upload = False
tls = False
cert = ""
key = ""
keypass = ""


# Utility function to guess the IP (as a string) where the server can be
# reached from the outside. Quite nasty problem actually.


def find_ip():
    # we get a UDP-socket for the TEST-networks reserved by IANA.
    # It is highly unlikely, that there is special routing used
    # for these networks, hence the socket later should give us
    # the ip address of the default route.
    # We're doing multiple tests, to guard against the computer being
    # part of a test installation.

    candidates = []
    for test_ip in ["192.0.2.0", "198.51.100.0", "203.0.113.0"]:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((test_ip, 80))
        ip_addr = s.getsockname()[0]
        s.close()
        if ip_addr in candidates:
            return ip_addr
        candidates.append(ip_addr)

    return candidates[0]


def decode_multipart_form_data(
    multipart_data: BinaryIO, headers: email.message.Message
) -> list[tuple[dict[str, str], bytes]]:
    """Decode multipart form data"""
    content_type = headers["Content-Type"].encode("ascii")
    content_len = int(headers["Content-Length"])
    data = multipart_data.read(content_len)

    content = b"Content-Type: %b\r\n%b" % (content_type, data)

    parsed = email.parser.BytesParser().parsebytes(content)

    results = []
    for part in parsed.get_payload():
        params = part.get_params(header="content-disposition")
        payload: bytes = part.get_payload(decode=True)
        result = dict(params), payload
        results.append(result)
    return results


# our own HTTP server class, fixing up a change in python 2.7
# since we do our fork() in the request handler
# the server must not shutdown() the socket.


class ForkingHTTPServer(http.server.HTTPServer):
    def process_request(self, request, client_address):
        self.finish_request(request, client_address)
        self.close_request(request)


# Main class implementing an HTTP-Requesthandler, that serves just a single
# file and redirects all other requests to this file (this passes the actual
# filename to the client).
# Currently it is impossible to serve different files with different
# instances of this class.


class FileServHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    server_version = "Simons FileServer"
    protocol_version = "HTTP/1.0"

    filename = "."

    def log_request(self, code="-", size="-"):
        if code == 200:
            super().log_request(code, size)

    def do_POST(self):
        global maxdownloads, upload

        if not upload:
            self.send_error(501, "Unsupported method (POST)")
            return

        multi_form = decode_multipart_form_data(self.rfile, self.headers)

        for form_dict, content in multi_form:
            if form_dict.get("name") == "upfile":
                break
        else:
            # Went through without break, did not find
            self.send_error(403, "No upload provided")
            return

        if not content or not form_dict.get("filename"):
            self.send_error(403, "No upload provided")
            return

        upfilename = form_dict["filename"]

        if "\\" in upfilename:
            upfilename = upfilename.rsplit("\\", 1)[-1]

        upfilename = os.path.basename(upfilename)

        destfile = None
        for suffix in ["", ".1", ".2", ".3", ".4", ".5", ".6", ".7", ".8", ".9"]:
            destfilename = os.path.join(".", upfilename + suffix)
            try:
                destfile = os.open(
                    destfilename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
                )
                break
            except OSError as ex:
                if ex.errno == errno.EEXIST:
                    continue
                raise

        if not destfile:
            upfilename += "."
            destfile, destfilename = tempfile.mkstemp(prefix=upfilename, dir=".")

        print(
            "Accepting uploaded file: %s -> %s" % (upfilename, destfilename),
            file=sys.stderr,
        )

        with BytesIO(content) as readfile:
            with open(destfile, "wb") as writefile:
                shutil.copyfileobj(readfile, writefile)

        # if upfile.done == -1:
        #   self.send_error (408, "upload interrupted")

        txt = b"""\
              <!DOCTYPE html>
              <html>
                <head><title>Wurf Upload</title></head>
                <body>
                  <h1>Wurf Upload complete</title></h1>
                  <p>Thanks a lot!</p>
                </body>
              </html>
            """
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(txt)))
        self.end_headers()
        self.wfile.write(txt)

        maxdownloads -= 1

        return

    def do_GET(self):
        global maxdownloads, cpid, compressed, upload

        # Form for uploading a file
        if upload:
            txt = b"""\
                 <!DOCTYPE html>
                 <html>
                   <head><title>Wurf Upload</title></head>
                   <body>
                     <h1>Wurf Upload</title></h1>
                     <form name="upload" method="POST" enctype="multipart/form-data">
                       <p><input type="file" name="upfile" /></p>
                       <p><input type="submit" value="Upload!" /></p>
                     </form>
                   </body>
                 </html>
               """
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(txt)))
            self.end_headers()
            self.wfile.write(txt)
            return

        # Redirect any request to the filename of the file to serve.
        # This hands over the filename to the client.

        self.path = urllib.parse.quote(urllib.parse.unquote(self.path))
        location = "/" + urllib.parse.quote(os.path.basename(self.filename))
        if os.path.isdir(self.filename):
            if compressed == "gz":
                location += ".tar.gz"
            elif compressed == "bz2":
                location += ".tar.bz2"
            elif compressed == "zip":
                location += ".zip"
            else:
                location += ".tar"

        if self.path != location:
            txt = (
                """\
                <!DOCTYPE html>
                <html>
                   <head><title>302 Found</title></head>
                   <body>302 Found <a href="%s">here</a>.</body>
                </html>\n"""
                % location
            )
            txt = txt.encode("ascii")
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(txt)))
            self.end_headers()
            self.wfile.write(txt)
            return

        maxdownloads -= 1

        # let a separate process handle the actual download, so that
        # multiple downloads can happen simultaneously.

        cpid = os.fork()

        if cpid == 0:
            # Child process
            type = None

            if os.path.isfile(self.filename):
                type = "file"
            elif os.path.isdir(self.filename):
                type = "dir"

            if not type:
                print("can only serve files or directories. Aborting.", file=sys.stderr)
                sys.exit(1)

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header(
                "Content-Disposition",
                "attachment;filename=%s"
                % urllib.parse.quote(
                    os.path.basename(self.filename + self.archive_ext)
                ),
            )
            if os.path.isfile(self.filename):
                self.send_header("Content-Length", str(os.path.getsize(self.filename)))
            self.end_headers()

            try:
                if type == "file":
                    with open(self.filename, "rb") as datafile:
                        shutil.copyfileobj(datafile, self.wfile)
                elif type == "dir":
                    if compressed == "zip":
                        with zipfile.ZipFile(
                            self.wfile, "w", zipfile.ZIP_DEFLATED
                        ) as zfile:
                            stripoff = os.path.dirname(self.filename) + os.sep

                            for root, dirs, files in os.walk(self.filename):
                                for f in files:
                                    filename = os.path.join(root, f)
                                    if filename[: len(stripoff)] != stripoff:
                                        raise RuntimeError(
                                            "invalid filename assumptions, please report!"
                                        )
                                    zfile.write(filename, filename[len(stripoff) :])
                    else:
                        with tarfile.open(
                            mode=("w|" + compressed), fileobj=self.wfile
                        ) as tfile:
                            tfile.add(
                                self.filename, arcname=os.path.basename(self.filename)
                            )

            except Exception as ex:
                print(ex)
                print("Connection broke. Aborting", file=sys.stderr)


def serve_files(filename, maxdown=1, ip_addr="", port=8080):
    global maxdownloads

    maxdownloads = maxdown

    archive_ext = ""
    if filename and os.path.isdir(filename):
        if compressed == "gz":
            archive_ext = ".tar.gz"
        elif compressed == "bz2":
            archive_ext = ".tar.bz2"
        elif compressed == "zip":
            archive_ext = ".zip"
        else:
            archive_ext = ".tar"

    # We have to somehow push the filename of the file to serve to the
    # class handling the requests. This is an evil way to do this...

    FileServHTTPRequestHandler.filename = filename
    FileServHTTPRequestHandler.archive_ext = archive_ext

    try:
        httpd = ForkingHTTPServer((ip_addr, port), FileServHTTPRequestHandler)
    except socket.error:
        print(
            "cannot bind to IP address '%s' port %d" % (ip_addr, port), file=sys.stderr
        )
        sys.exit(1)
    listen_protocol = "https" if tls else "http"
    if not ip_addr:
        ip_addr = find_ip()
    if ip_addr:
        if filename:
            location = f"{listen_protocol}://{ip_addr}:{httpd.server_port}/" + urllib.parse.quote(
                os.path.basename(filename + archive_ext)
            )
        else:
            location = "%s://%s:%s/" % (listen_protocol, ip_addr, httpd.server_port)

        print("Now serving on %s" % location)
    if tls :
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            context.load_cert_chain(cert, key, keypass)
        except ssl.SSLError:
            print("Unable to load certificate or key. Possibly missing or incorrect password.")
            sys.exit(1)
        except FileNotFoundError:
            print("Certificate or Key file is inaccessible or incorrect.")
            sys.exit(1)

        with context.wrap_socket(httpd.socket, server_side=True) as ssock:
            httpd.socket = ssock
            while cpid != 0 and maxdownloads > 0:
                httpd.handle_request()
    else:
        while cpid != 0 and maxdownloads > 0:
            httpd.handle_request()


def usage(defport, defmaxdown, errmsg=None):
    name = os.path.basename(sys.argv[0])
    print(
        """
    Usage: %s [-i <ip_addr>] [-p <port>] [-c <count>] [-t [--cert <cert_file>] [--key <key_file>] [--keypass <key_pass>]] <file>
           %s [-i <ip_addr>] [-p <port>] [-c <count>] [-t [--cert <cert_file>] [--key <key_file>] [--keypass <key_pass>]] [-z|-j|-Z|-u] <dir>
           %s [-i <ip_addr>] [-p <port>] [-c <count>] [-t [--cert <cert_file>] [--key <key_file>] [--keypass <key_pass>]] -s
           %s [-i <ip_addr>] [-p <port>] [-c <count>] [-t [--cert <cert_file>] [--key <key_file>] [--keypass <key_pass>]] -U

           %s <url>

    Serves a single file <count> times via http on port <port> on IP
    address <ip_addr>.
    When a directory is specified, an tar archive gets served. By default
    it is gzip compressed. You can specify -z for gzip compression,
    -j for bzip2 compression, -Z for ZIP compression or -u for no compression.
    You can configure your default compression method in the configuration
    file described below.

    When -t is specified, wurf will use TLS to secure the connection. You must pass both a certificate and key in PEM format.

    When -s is specified instead of a filename, %s distributes itself.

    When -U is specified, wurf provides an upload form, allowing file uploads.

    defaults: count = %d, port = %d

    If started with an url as an argument, wurf acts as a client,
    downloading the file and saving it in the current directory.

    You can specify different defaults in two locations: /etc/wurfrc
    and ~/.wurfrc can be INI-style config files containing the default
    port and the default count. The file in the home directory takes
    precedence. The compression methods are "off", "gz", "bz2" or "zip".

    Sample file:

        [main]
        port = 8008
        count = 2
        ip = 127.0.0.1
        compressed = gz
        tls = on

        [tls]
        cert = /etc/letsencrypt/live/example.com/fullchain.pem
        key = /etc/letsencrypt/live/example.com/privkey.pem
        keypass = my_password
   """
        % (name, name, name, name, name, name, defmaxdown, defport),
        file=sys.stderr,
    )

    if errmsg:
        print(errmsg, file=sys.stderr)
        print(file=sys.stderr)
    sys.exit(1)


def wurf_client(url):
    urlparts = urllib.parse.urlparse(url, "http")
    if urlparts[0] not in ["http", "https"] or urlparts[1] == "":
        return None

    fname = None

    f = urllib.request.urlopen(url)

    f_meta = f.info()
    disp = f_meta["Content-Disposition"]

    if disp:
        disp = disp.split(";")

    if disp and disp[0].lower() == "attachment":
        fname = [x[9:] for x in disp[1:] if x[:9].lower() == "filename="]
        if len(fname):
            fname = fname[0]
        else:
            fname = None

    if fname == None:
        url = f.geturl()
        urlparts = urllib.parse.urlparse(url)
        fname = urlparts[2]

    if not fname:
        fname = "wurf-out.bin"

    if fname:
        fname = urllib.parse.unquote(fname)
        fname = os.path.basename(fname)

    readline.set_startup_hook(lambda: readline.insert_text(fname))
    fname = input("Enter target filename: ")
    readline.set_startup_hook(None)

    override = False

    destfile = None
    destfilename = os.path.join(".", fname)
    try:
        destfile = os.open(destfilename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    except OSError as e:
        if e.errno == errno.EEXIST:
            override = input("File exists. Overwrite (y/n)? ")
            override = override.lower() in ["y", "yes"]
        else:
            raise

    if destfile == None:
        if override == True:
            destfile = os.open(destfilename, os.O_WRONLY | os.O_CREAT, 0o644)
        else:
            for suffix in [".1", ".2", ".3", ".4", ".5", ".6", ".7", ".8", ".9"]:
                destfilename = os.path.join(".", fname + suffix)
                try:
                    destfile = os.open(
                        destfilename, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644
                    )
                    break
                except OSError as e:
                    if e.errno == errno.EEXIST:
                        continue
                    raise

            if not destfile:
                destfile, destfilename = tempfile.mkstemp(prefix=fname + ".", dir=".")
            print("alternate filename is:", destfilename)

    print("downloading file: %s -> %s" % (fname, destfilename))

    shutil.copyfileobj(f, os.fdopen(destfile, "wb"))

    return 1


def main():
    global cpid, upload, compressed, tls, cert, key, keypass

    maxdown = 1
    port = 8080
    ip_addr = ""

    config = configparser.ConfigParser()
    config.read(
        [
            "/etc/woofrc",
            "/etc/wurfrc",
            os.path.expanduser("~/.woofrc"),
            os.path.expanduser("~/.wurfrc"),
        ]
    )

    if config.has_option("main", "port"):
        port = config.getint("main", "port")

    if config.has_option("main", "count"):
        maxdown = config.getint("main", "count")

    if config.has_option("main", "ip"):
        ip_addr = config.get("main", "ip")

    if config.has_option("main", "compressed"):
        formats = {
            "gz": "gz",
            "true": "gz",
            "bz": "bz2",
            "bz2": "bz2",
            "zip": "zip",
            "off": "",
            "false": "",
        }
        compressed = config.get("main", "compressed")
        compressed = formats.get(compressed, "gz")

    if config.has_option("main", "tls"):
        affirm = {
            "yes": True,
            "true": True,
            "enabled": True,
            "on": True
        }
        tls_setting = config.get("main", "tls")
        tls = affirm.get(tls_setting, False)
        if not config.has_option("main", "port"):
            port = 8443

    if config.has_option("tls", "cert"):
        cert = config.get("tls", "cert")

    if config.has_option("tls", "key"):
        key = config.get("tls", "key")

    if config.has_option("tls", "keypass"):
        keypass = config.get("tls", "keypass")

    defaultport = port
    defaultmaxdown = maxdown

    try:
        options, filenames = getopt.gnu_getopt(sys.argv[1:], "hUszjZuti:c:p:", ["cert=", "key=", "keypass="])
    except getopt.GetoptError as desc:
        usage(defaultport, defaultmaxdown, desc)

    for option, val in options:
        if option == "-c":
            try:
                maxdown = int(val)
                if maxdown <= 0:
                    raise ValueError
            except ValueError:
                usage(
                    defaultport,
                    defaultmaxdown,
                    "invalid download count: %r. "
                    "Please specify an integer >= 0." % val,
                )

        elif option == "-i":
            ip_addr = val

        elif option == "-p":
            try:
                port = int(val)
            except ValueError:
                usage(
                    defaultport,
                    defaultmaxdown,
                    "invalid port number: %r. Please specify an integer" % val,
                )

        elif option == "-s":
            filenames.append(__file__)

        elif option == "-h":
            usage(defaultport, defaultmaxdown)

        elif option == "-U":
            upload = True

        elif option == "-z":
            compressed = "gz"
        elif option == "-j":
            compressed = "bz2"
        elif option == "-Z":
            compressed = "zip"
        elif option == "-u":
            compressed = ""

        elif option == "-t":
            tls = True
            if '-p' not in dict(options) and not config.has_option("main", "port"):
                port = 8443
        elif option == "--cert":
            cert = val
        elif option == "--key":
            key = val
        elif option == "--keypass":
            keypass = val

        else:
            usage(defaultport, defaultmaxdown, "Unknown option: %r" % option)

    if upload:
        if len(filenames) > 0:
            usage(
                defaultport,
                defaultmaxdown,
                "Conflicting usage: simultaneous up- and download not supported.",
            )
        filename = None

    else:
        if len(filenames) == 1:
            if wurf_client(filenames[0]) != None:
                sys.exit(0)

            filename = os.path.abspath(filenames[0])
        else:
            usage(
                defaultport, defaultmaxdown, "Can only serve single files/directories."
            )

        if not os.path.exists(filename):
            usage(
                defaultport,
                defaultmaxdown,
                "%s: No such file or directory" % filenames[0],
            )

        if not (os.path.isfile(filename) or os.path.isdir(filename)):
            usage(
                defaultport,
                defaultmaxdown,
                "%s: Neither file nor directory" % filenames[0],
            )

    if tls:
        if cert == "" or key == "":
            usage(
                defaultport,
                defaultmaxdown,
                "Missing option, TLS requested but certificate/key pair not provided",
            )

    serve_files(filename, maxdown, ip_addr, port)

    # wait for child processes to terminate
    if cpid != 0:
        try:
            while 1:
                os.wait()
        except OSError:
            pass


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
