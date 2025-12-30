# NetStacks Wiki Documentation

This folder contains the documentation for the NetStacks GitHub Wiki.

## Setup Instructions

To publish this documentation to the GitHub Wiki:

### Option 1: Initialize Wiki via GitHub Web Interface

1. Go to https://github.com/viperbmw/netstacks
2. Click on the **Wiki** tab
3. Click **Create the first page**
4. Add initial content and save
5. This creates the wiki repository

Then push the content:

```bash
# Clone the wiki repository
git clone https://github.com/viperbmw/netstacks.wiki.git
cd netstacks.wiki

# Copy wiki files
cp ../netstacks/docs/wiki/*.md .

# Commit and push
git add .
git commit -m "Initial wiki documentation"
git push
```

### Option 2: Using GitHub CLI

```bash
# If wiki is enabled, clone and push
gh repo clone viperbmw/netstacks.wiki
cp docs/wiki/*.md ../netstacks.wiki/
cd ../netstacks.wiki
git add . && git commit -m "Initial wiki" && git push
```

## Wiki Structure

| Page | Description |
|------|-------------|
| Home.md | Wiki homepage with navigation |
| _Sidebar.md | Sidebar navigation |
| Installation.md | Deployment guide |
| Configuration.md | Settings and environment |
| Quick-Start-Guide.md | Getting started tutorial |
| Device-Management.md | Managing network devices |
| Templates.md | Configuration templates |
| Service-Stacks.md | Template grouping |
| MOPs.md | Method of Procedures |
| Configuration-Backups.md | Backup system |
| AI-Agents.md | AI automation |
| Authentication.md | Auth setup |
| API-Reference.md | REST API docs |
| Architecture.md | System design |
| Developer-Guide.md | Contributing |
| Troubleshooting.md | Common issues |

## Editing

To update the wiki:

1. Edit files in this folder
2. Commit to main repository
3. Copy updated files to wiki repository
4. Push wiki repository

Or edit directly on GitHub wiki interface.
