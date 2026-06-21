# Cockpit terminal — Forsch ADK workspace (sourced by the embedded terminal's bash)
export PATH="/root/.local/bin:$PATH"        # uv, and other ~/.local tools
export EDITOR=nano
export CLICOLOR=1
export TERM=xterm-256color
export GIT_PAGER=cat
export PAGER='less -R'
export IS_SANDBOX=1                                     # single-purpose box -> allow claude bypass as root
alias claude='claude --dangerously-skip-permissions'    # full autonomy by default in this terminal

alias ls='ls --color=auto'
alias ll='ls -alhF --color=auto'
alias gs='git status -sb'
alias gd='git diff'
alias gl='git log --oneline -15'

# warm, legible prompt:  hubert  <cwd>  ❯
PS1='\[\e[38;5;108m\]hubert\[\e[0m\] \[\e[38;5;180m\]\w\[\e[0m\] \[\e[38;5;244m\]❯\[\e[0m\] '

cd /root/.hermes/workspace/adk 2>/dev/null

printf '\e[38;5;108m  Forsch ADK workspace\e[0m  ·  tmux session "ops" (persistent across reconnects)\n'
printf '  \e[38;5;244mhere\e[0m   ~/.hermes/workspace/adk\n'
printf '  \e[38;5;244mclaude\e[0m %s   \e[38;5;244m(run `claude` — Claude, root + full bypass autonomy; first run prompts to log in)\e[0m\n' "$(claude --version 2>/dev/null | awk "{print \$1}")"
printf '  \e[38;5;244mdeploy\e[0m docker restart adk-bridge   \e[38;5;244m(or the Deploy button up top)\e[0m\n'
printf '  \e[38;5;244medit\e[0m   the ✎ buttons in the Toolbox open files here\n\n'
