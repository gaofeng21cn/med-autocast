#!/usr/bin/env python3
"""Explicit invocation of one registered Workbench tool, with its original effects."""
import argparse
from pathlib import Path
from workbench_adapter import run_tool, TOOLS

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,required=True)
    parser.add_argument('--name',choices=sorted(TOOLS),required=True)
    parser.add_argument('--bundled',action='store_true')
    parser.add_argument('arguments',nargs=argparse.REMAINDER)
    a=parser.parse_args()
    root=a.workspace.resolve()
    if not (root/'workbench.yaml').is_file():
        parser.error('workspace 必须包含 workbench.yaml')
    args=a.arguments[1:] if a.arguments[:1]==['--'] else a.arguments
    return run_tool(root,a.name,args,a.bundled)

if __name__=='__main__':raise SystemExit(main())
