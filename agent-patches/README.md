# Agent Patches

This folder containes automated patches for installers. Generally, they should be able to be ran by doing:
```bash
cat utils/new-agents | tr '|' '\n' | xargs -I {} ./script.sh {}
```

The above command should run the script over each "new" agent.
