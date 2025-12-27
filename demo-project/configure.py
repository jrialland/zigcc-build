from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from zigcc_build.config import ZigCcConfig

def configure(config: "ZigCcConfig"):
    print("Running custom configuration...")
    # Add a define dynamically
    config["defines"].append("DYNAMIC_MACRO=1")
    
    # We could also add sources dynamically
    # config["sources"].append("src/extra.c")
