# wurf - Web Upload and Receive Files

## Rationale

I guess everybody with a laptop has experienced this problem at some
point: You plug into a network and just want to exchange files with
other participants. It *always* is a pain until you can exchange
files with the person vis-a-vis.

Of course there are a lot of tools to tackle this problem. For large
scale communities there are dozens of filesharing networks. However,
they don't work for small local networks. Of course you could put your
stuff to exchange on a local web server, but who really wants to
maintain this? Tools like the ingenious
[npush/npoll](http://www.fefe.de/ncp/) are
extremely helpful, provided that both parties have it installed,
[SAFT](http://www.belwue.de/projekte/saft/)
also aims to solve this problem, but needs a permanently running daemon...

**wurf** (Web Upload and Receive Files) tries a different approach. It
assumes that everybody has a web-browser or a commandline web-client
installed. The **wurf** command is a small simple webserver that can
easily be invoked on a single file. Your partner can access the file
with tools he trusts (e.g. **wget**). No need to enter
passwords on keyboards where you don't know about keyboard sniffers, no
need to start a huge lot of infrastructure, just do a
```
     $ wurf filename
```
and tell the recipient the URL **wurf** spits out. When he got that
file, **wurf** will quit and everything is done.

And when someone wants to send you a file, **wurf** has a switch
to offer itself, so he can get **wurf** and offer a file to you.

## Prerequisites and usage

**wurf** needs Python on a unix'ish operating system. Some people
have used it successfully on Windows within the cygwin environment.

```
    Usage: wurf [-i <ip_addr>] [-p <port>] [-c <count>] <file>
           wurf [-i <ip_addr>] [-p <port>] [-c <count>] [-z|-j|-Z|-u] <dir>
           wurf [-i <ip_addr>] [-p <port>] [-c <count>] -s
           wurf [-i <ip_addr>] [-p <port>] [-c <count>] -U
   
           wurf <url>

    Serves a single file <count> times via http on port <port> on IP
    address <ip_addr>.
    When a directory is specified, an tar archive gets served. By default
    it is gzip compressed. You can specify -z for gzip compression, 
    -j for bzip2 compression, -Z for ZIP compression or -u for no compression.
    You can configure your default compression method in the configuration 
    file described below.

    When -s is specified instead of a filename, wurf distributes itself.

    When -U is specified, wurf provides an upload form, allowing file uploads.
   
    defaults: count = 1, port = 8080

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
```

## Credits

wurf is a fork of woof by Simon Budig <simon@budig.de>
