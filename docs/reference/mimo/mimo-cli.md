# MiMo CLI (mimocode) — local reference

The orchestrator CLI the chat surface shells out to. Captured from `mimo --help` + subcommand help on 2026-06-29T02:46:19Z.

## mimo --help
```
⠀                                       
█▀▄▀█ █ █▄ ▄█ █▀▀█ █▀▀ █▀▀█ █▀▀▄ █▀▀▀
█ ▀ █ █ █ ▀ █ █  █ █   █  █ █  █ █▀▀ 
▀   ▀ ▀ ▀   ▀ ▀▀▀▀ ▀▀▀ ▀▀▀▀ ▀▀▀  ▀▀▀▀

Commands:
  mimo completion          generate shell completion script
  mimo acp                 start ACP (Agent Client Protocol) server
  mimo mcp                 manage MCP (Model Context Protocol) servers
  mimo [project]           start mimocode tui                                              [default]
  mimo attach <url>        attach to a running mimocode server
  mimo run [message..]     run mimocode with a message
  mimo debug               debugging and troubleshooting tools
  mimo providers           manage AI providers and credentials                       [aliases: auth]
  mimo agent               manage agents
  mimo upgrade [target]    upgrade mimocode to the latest or a specific version
  mimo uninstall           uninstall mimocode and remove all related files
  mimo serve               starts a headless mimocode server
  mimo models [provider]   list all available models
  mimo stats               show token usage and cost statistics
  mimo export [sessionID]  export session data as JSON
  mimo import <file>       import session data from JSON file or URL
  mimo github              manage GitHub agent
  mimo pr <number>         fetch and checkout a GitHub PR branch, then run mimocode
  mimo session             manage sessions
  mimo plugin <module>     install plugin and update config                          [aliases: plug]
  mimo db                  database tools

Positionals:
  project  path to start mimocode in                                                        [string]

Options:
  -h, --help         show help                                                             [boolean]
  -v, --version      show version number                                                   [boolean]
      --print-logs   print logs to stderr                                                  [boolean]
      --log-level    log level                  [string] [choices: "DEBUG", "INFO", "WARN", "ERROR"]
      --pure         run without external plugins                                          [boolean]
      --port         port to listen on                                         [number] [default: 0]
      --hostname     hostname to listen on                           [string] [default: "127.0.0.1"]
      --mdns         enable mDNS service discovery (defaults hostname to 0.0.0.0)
                                                                          [boolean] [default: false]
      --mdns-domain  custom domain name for mDNS service (default: mimocode.local)
                                                                [string] [default: "mimocode.local"]
      --cors         additional domains to allow for CORS                      [array] [default: []]
      --no-auth      allow starting without authentication on non-loopback addresses (DANGEROUS)
                                                                          [boolean] [default: false]
  -m, --model        model to use in the format of provider/model                           [string]
  -c, --continue     continue the last session                                             [boolean]
  -s, --session      session id to continue                                                 [string]
      --fork         fork the session when continuing (use with --continue or --session)   [boolean]
      --prompt       prompt to use                                                          [string]
      --agent        agent to use                                                           [string]
      --never-ask    start in never-ask mode — auto-decide without asking (permissions excluded),
                     toggle at runtime with /never-ask                    [boolean] [default: false]
      --trust        skip workspace trust prompt and trust the directory  [boolean] [default: false]```

## mimo run --help
```
mimo run [message..]

run mimocode with a message

Positionals:
  message  message to send                                                     [array] [default: []]

Options:
  -h, --help                          show help                                            [boolean]
  -v, --version                       show version number                                  [boolean]
      --print-logs                    print logs to stderr                                 [boolean]
      --log-level                     log level [string] [choices: "DEBUG", "INFO", "WARN", "ERROR"]
      --pure                          run without external plugins                         [boolean]
      --command                       the command to run, use message for args              [string]
  -c, --continue                      continue the last session                            [boolean]
  -s, --session                       session id to continue                                [string]
      --fork                          fork the session before continuing (requires --continue or
                                      --session)                                           [boolean]
      --share                         share the session                                    [boolean]
  -m, --model                         model to use in the format of provider/model          [string]
      --agent                         agent to use                                          [string]
      --format                        format: default (formatted) or json (raw JSON events)
                                          [string] [choices: "default", "json"] [default: "default"]
  -f, --file                          file(s) to attach to message                           [array]
      --title                         title for the session (uses truncated prompt if no value
                                      provided)                                             [string]
      --attach                        attach to a running mimocode server (e.g.,
                                      http://localhost:4096)                                [string]
  -p, --password                      basic auth password (defaults to MIMOCODE_SERVER_PASSWORD)
                                                                                            [string]
      --dir                           directory to run in, path on remote server if attaching
                                                                                            [string]
      --port                          port for the local server (defaults to random port if no value
                                      provided)                                             [number]
      --variant                       model variant (provider-specific reasoning effort, e.g., high,
                                      max, minimal)                                         [string]
      --thinking                      show thinking blocks                [boolean] [default: false]
      --dangerously-skip-permissions  auto-approve permissions that are not explicitly denied
                                      (dangerous!)                        [boolean] [default: false]```

## mimo agent --help
```
mimo agent

manage agents

Commands:
  mimo agent create  create a new agent
  mimo agent list    list all available agents

Options:
  -h, --help        show help                                                              [boolean]
  -v, --version     show version number                                                    [boolean]
      --print-logs  print logs to stderr                                                   [boolean]
      --log-level   log level                   [string] [choices: "DEBUG", "INFO", "WARN", "ERROR"]
      --pure        run without external plugins                                           [boolean]```

## mimo mcp --help
```
mimo mcp

manage MCP (Model Context Protocol) servers

Commands:
  mimo mcp add            add an MCP server
  mimo mcp list           list MCP servers and their status                            [aliases: ls]
  mimo mcp auth [name]    authenticate with an OAuth-enabled MCP server
  mimo mcp logout [name]  remove OAuth credentials for an MCP server
  mimo mcp debug <name>   debug OAuth connection for an MCP server

Options:
  -h, --help        show help                                                              [boolean]
  -v, --version     show version number                                                    [boolean]
      --print-logs  print logs to stderr                                                   [boolean]
      --log-level   log level                   [string] [choices: "DEBUG", "INFO", "WARN", "ERROR"]
      --pure        run without external plugins                                           [boolean]```

## mimo providers --help
```
mimo providers

manage AI providers and credentials

Commands:
  mimo providers list         list providers and credentials                           [aliases: ls]
  mimo providers login [url]  log in to a provider
  mimo providers logout       log out from a configured provider
  mimo providers whoami       show current logged-in user info

Options:
  -h, --help        show help                                                              [boolean]
  -v, --version     show version number                                                    [boolean]
      --print-logs  print logs to stderr                                                   [boolean]
      --log-level   log level                   [string] [choices: "DEBUG", "INFO", "WARN", "ERROR"]
      --pure        run without external plugins                                           [boolean]```

## mimo acp --help
```
mimo acp

start ACP (Agent Client Protocol) server

Options:
  -h, --help         show help                                                             [boolean]
  -v, --version      show version number                                                   [boolean]
      --print-logs   print logs to stderr                                                  [boolean]
      --log-level    log level                  [string] [choices: "DEBUG", "INFO", "WARN", "ERROR"]
      --pure         run without external plugins                                          [boolean]
      --port         port to listen on                                         [number] [default: 0]
      --hostname     hostname to listen on                           [string] [default: "127.0.0.1"]
      --mdns         enable mDNS service discovery (defaults hostname to 0.0.0.0)
                                                                          [boolean] [default: false]
      --mdns-domain  custom domain name for mDNS service (default: mimocode.local)
                                                                [string] [default: "mimocode.local"]
      --cors         additional domains to allow for CORS                      [array] [default: []]
      --no-auth      allow starting without authentication on non-loopback addresses (DANGEROUS)
                                                                          [boolean] [default: false]
      --cwd          working directory             [string] [default: "/root/.hermes/workspace/adk"]```

## mimo debug --help
```
mimo debug

debugging and troubleshooting tools

Commands:
  mimo debug config        show resolved configuration
  mimo debug lsp           LSP debugging utilities
  mimo debug rg            ripgrep debugging utilities
  mimo debug file          file system debugging utilities
  mimo debug scrap         list all known projects
  mimo debug skill         list all available skills
  mimo debug snapshot      snapshot debugging utilities
  mimo debug agent <name>  show agent configuration details
  mimo debug paths         show global paths (data, config, cache, state)
  mimo debug wait          wait indefinitely (for debugging)

Options:
  -h, --help        show help                                                              [boolean]
  -v, --version     show version number                                                    [boolean]
      --print-logs  print logs to stderr                                                   [boolean]
      --log-level   log level                   [string] [choices: "DEBUG", "INFO", "WARN", "ERROR"]
      --pure        run without external plugins                                           [boolean]```

## mimo attach --help
```
mimo attach <url>

attach to a running mimocode server

Positionals:
  url  http://localhost:4096                                                     [string] [required]

Options:
  -h, --help        show help                                                              [boolean]
  -v, --version     show version number                                                    [boolean]
      --print-logs  print logs to stderr                                                   [boolean]
      --log-level   log level                   [string] [choices: "DEBUG", "INFO", "WARN", "ERROR"]
      --pure        run without external plugins                                           [boolean]
      --dir         directory to run in                                                     [string]
  -c, --continue    continue the last session                                              [boolean]
  -s, --session     session id to continue                                                  [string]
      --fork        fork the session when continuing (use with --continue or --session)    [boolean]
  -p, --password    basic auth password (defaults to MIMOCODE_SERVER_PASSWORD)              [string]```

## mimo completion --help
```
⠀                                       
█▀▄▀█ █ █▄ ▄█ █▀▀█ █▀▀ █▀▀█ █▀▀▄ █▀▀▀
█ ▀ █ █ █ ▀ █ █  █ █   █  █ █  █ █▀▀ 
▀   ▀ ▀ ▀   ▀ ▀▀▀▀ ▀▀▀ ▀▀▀▀ ▀▀▀  ▀▀▀▀

Commands:
  mimo completion          generate shell completion script
  mimo acp                 start ACP (Agent Client Protocol) server
  mimo mcp                 manage MCP (Model Context Protocol) servers
  mimo [project]           start mimocode tui                                              [default]
  mimo attach <url>        attach to a running mimocode server
  mimo run [message..]     run mimocode with a message
  mimo debug               debugging and troubleshooting tools
  mimo providers           manage AI providers and credentials                       [aliases: auth]
  mimo agent               manage agents
  mimo upgrade [target]    upgrade mimocode to the latest or a specific version
  mimo uninstall           uninstall mimocode and remove all related files
  mimo serve               starts a headless mimocode server
  mimo models [provider]   list all available models
  mimo stats               show token usage and cost statistics
  mimo export [sessionID]  export session data as JSON
  mimo import <file>       import session data from JSON file or URL
  mimo github              manage GitHub agent
  mimo pr <number>         fetch and checkout a GitHub PR branch, then run mimocode
  mimo session             manage sessions
  mimo plugin <module>     install plugin and update config                          [aliases: plug]
  mimo db                  database tools

Positionals:
  project  path to start mimocode in                                                        [string]

Options:
  -h, --help         show help                                                             [boolean]
  -v, --version      show version number                                                   [boolean]
      --print-logs   print logs to stderr                                                  [boolean]
      --log-level    log level                  [string] [choices: "DEBUG", "INFO", "WARN", "ERROR"]
      --pure         run without external plugins                                          [boolean]
      --port         port to listen on                                         [number] [default: 0]
      --hostname     hostname to listen on                           [string] [default: "127.0.0.1"]
      --mdns         enable mDNS service discovery (defaults hostname to 0.0.0.0)
                                                                          [boolean] [default: false]
      --mdns-domain  custom domain name for mDNS service (default: mimocode.local)
                                                                [string] [default: "mimocode.local"]
      --cors         additional domains to allow for CORS                      [array] [default: []]
      --no-auth      allow starting without authentication on non-loopback addresses (DANGEROUS)
                                                                          [boolean] [default: false]
  -m, --model        model to use in the format of provider/model                           [string]
  -c, --continue     continue the last session                                             [boolean]
  -s, --session      session id to continue                                                 [string]
      --fork         fork the session when continuing (use with --continue or --session)   [boolean]
      --prompt       prompt to use                                                          [string]
      --agent        agent to use                                                           [string]
      --never-ask    start in never-ask mode — auto-decide without asking (permissions excluded),
                     toggle at runtime with /never-ask                    [boolean] [default: false]
      --trust        skip workspace trust prompt and trust the directory  [boolean] [default: false](unavailable)
```
