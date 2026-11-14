/** Standalone symbol contracts; copied as data, with no dependency on the UI package. */
export const TYPE_CONTRACTS = [
  {
    "type": "digester",
    "label": "Anaerobic digester",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "biogas",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "drive",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "ruptured",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "tank",
    "label": "Storage tank",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "ruptured",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "gas-holder",
    "label": "Gas holder",
    "ports": [
      {
        "id": "inlet",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "gas",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "ruptured",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "mixing-tank",
    "label": "Mixing tank",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "drive",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "ruptured",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "reactor",
    "label": "Pressure reactor",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "vent",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "gas-inlet",
        "medium": "gas",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "ruptured",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "clarifier",
    "label": "Circular clarifier",
    "ports": [
      {
        "id": "feed",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "effluent",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "sludge",
        "medium": "sludge",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "ruptured",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "silo",
    "label": "Bulk solids silo",
    "ports": [
      {
        "id": "fill",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "discharge",
        "medium": "solids",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "ruptured",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "heat-exchanger",
    "label": "Heat exchanger",
    "ports": [
      {
        "id": "hot-in",
        "medium": "thermal-fluid",
        "direction": "in"
      },
      {
        "id": "hot-out",
        "medium": "thermal-fluid",
        "direction": "out"
      },
      {
        "id": "cold-in",
        "medium": "thermal-fluid",
        "direction": "in"
      },
      {
        "id": "cold-out",
        "medium": "thermal-fluid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 60,
        "min": -20,
        "max": 300,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "fouled",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "filter",
    "label": "Media filter",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "backwash",
        "medium": "liquid",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "fouled",
          "leaking",
          "ruptured"
        ]
      }
    }
  },
  {
    "type": "gas-treatment",
    "label": "Gas treatment train",
    "ports": [
      {
        "id": "inlet",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "drive",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "fouled",
          "leaking",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "boiler",
    "label": "Gas-fired boiler",
    "ports": [
      {
        "id": "fuel",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "heat",
        "medium": "thermal",
        "direction": "out"
      },
      {
        "id": "exhaust",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "steam",
        "medium": "steam",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 180,
        "min": -20,
        "max": 600,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "overheated",
          "refractory-damage",
          "fuel-leak"
        ]
      }
    }
  },
  {
    "type": "flare",
    "label": "Flare stack",
    "ports": [
      {
        "id": "fuel",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "exhaust",
        "medium": "gas",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "overheated",
          "refractory-damage",
          "fuel-leak"
        ]
      }
    }
  },
  {
    "type": "pump",
    "label": "Centrifugal pump",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "drive",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "cavitating",
          "leaking",
          "seized",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "submersible-pump",
    "label": "Submersible pump",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "drive",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "cavitating",
          "leaking",
          "seized",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "dosing-pump",
    "label": "Metering pump",
    "ports": [
      {
        "id": "suction",
        "medium": "chemical",
        "direction": "in"
      },
      {
        "id": "dose",
        "medium": "chemical",
        "direction": "out"
      },
      {
        "id": "drive",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "cavitating",
          "leaking",
          "seized",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "blower",
    "label": "Centrifugal blower",
    "ports": [
      {
        "id": "intake",
        "medium": "air",
        "direction": "in"
      },
      {
        "id": "discharge",
        "medium": "air",
        "direction": "out"
      },
      {
        "id": "drive",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "blade-damage",
          "seized",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "compressor",
    "label": "Reciprocating compressor",
    "ports": [
      {
        "id": "inlet",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "drive",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "cavitating",
          "leaking",
          "seized",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "motor",
    "label": "Electric motor",
    "ports": [
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "shaft",
        "medium": "mechanical",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "generator",
    "label": "Microturbine generator",
    "ports": [
      {
        "id": "fuel",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "output",
        "medium": "electricity",
        "direction": "out"
      },
      {
        "id": "exhaust",
        "medium": "gas",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "short-circuit",
          "overheated",
          "burnt"
        ]
      }
    }
  },
  {
    "type": "transformer",
    "label": "Power transformer",
    "ports": [
      {
        "id": "primary",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "secondary",
        "medium": "electricity",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "short-circuit",
          "overheated",
          "burnt"
        ]
      }
    }
  },
  {
    "type": "breaker",
    "label": "Circuit breaker",
    "ports": [
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "load",
        "medium": "electricity",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "open": {
        "type": "boolean",
        "default": true
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "short-circuit",
          "overheated",
          "burnt"
        ]
      }
    }
  },
  {
    "type": "busbar",
    "label": "Distribution bus",
    "ports": [
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "branch-a",
        "medium": "electricity",
        "direction": "out"
      },
      {
        "id": "branch-b",
        "medium": "electricity",
        "direction": "out"
      },
      {
        "id": "branch-c",
        "medium": "electricity",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "short-circuit",
          "overheated",
          "burnt"
        ]
      }
    }
  },
  {
    "type": "battery",
    "label": "Battery bank",
    "ports": [
      {
        "id": "dc",
        "medium": "electricity",
        "direction": "bidirectional"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "short-circuit",
          "overheated",
          "burnt"
        ]
      }
    }
  },
  {
    "type": "ups",
    "label": "Uninterruptible supply",
    "ports": [
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "load",
        "medium": "electricity",
        "direction": "out"
      },
      {
        "id": "battery",
        "medium": "electricity",
        "direction": "bidirectional"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "short-circuit",
          "overheated",
          "burnt"
        ]
      }
    }
  },
  {
    "type": "solar-panel",
    "label": "Solar array",
    "ports": [
      {
        "id": "dc",
        "medium": "electricity",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "short-circuit",
          "overheated",
          "burnt"
        ]
      }
    }
  },
  {
    "type": "electrical-meter",
    "label": "Net power indicator",
    "ports": [
      {
        "id": "measurement",
        "medium": "measurement",
        "direction": "in"
      },
      {
        "id": "signal",
        "medium": "data",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "drift",
          "broken",
          "fouled"
        ]
      }
    }
  },
  {
    "type": "gate-valve",
    "label": "Gate valve",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "open": {
        "type": "boolean",
        "default": true
      },
      "opening": {
        "type": "number",
        "default": 100,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "stuck",
          "leaking",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "control-valve",
    "label": "Control valve",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "control",
        "medium": "data",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "open": {
        "type": "boolean",
        "default": true
      },
      "opening": {
        "type": "number",
        "default": 100,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "stuck",
          "leaking",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "check-valve",
    "label": "Check valve",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "open": {
        "type": "boolean",
        "default": true
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "stuck",
          "leaking",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "relief-valve",
    "label": "Pressure relief valve",
    "ports": [
      {
        "id": "inlet",
        "medium": "fluid",
        "direction": "in"
      },
      {
        "id": "relief",
        "medium": "fluid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "open": {
        "type": "boolean",
        "default": true
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "stuck",
          "leaking",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "butterfly-valve",
    "label": "Butterfly valve",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "open": {
        "type": "boolean",
        "default": true
      },
      "opening": {
        "type": "number",
        "default": 100,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "stuck",
          "leaking",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "pressure-transmitter",
    "label": "Pressure transmitter",
    "ports": [
      {
        "id": "process",
        "medium": "measurement",
        "direction": "in"
      },
      {
        "id": "signal",
        "medium": "data",
        "direction": "out"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "value": {
        "type": "number",
        "default": 42,
        "min": -9999,
        "max": 9999
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "drift",
          "broken",
          "fouled"
        ]
      }
    }
  },
  {
    "type": "flow-meter",
    "label": "Inline flow meter",
    "ports": [
      {
        "id": "process",
        "medium": "measurement",
        "direction": "in"
      },
      {
        "id": "signal",
        "medium": "data",
        "direction": "out"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "value": {
        "type": "number",
        "default": 42,
        "min": -9999,
        "max": 9999
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "drift",
          "broken",
          "fouled"
        ]
      }
    }
  },
  {
    "type": "temperature-sensor",
    "label": "Temperature probe",
    "ports": [
      {
        "id": "process",
        "medium": "measurement",
        "direction": "in"
      },
      {
        "id": "signal",
        "medium": "data",
        "direction": "out"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "value": {
        "type": "number",
        "default": 42,
        "min": -9999,
        "max": 9999
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "drift",
          "broken",
          "fouled"
        ]
      }
    }
  },
  {
    "type": "level-sensor",
    "label": "Level transmitter",
    "ports": [
      {
        "id": "process",
        "medium": "measurement",
        "direction": "in"
      },
      {
        "id": "signal",
        "medium": "data",
        "direction": "out"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "value": {
        "type": "number",
        "default": 42,
        "min": -9999,
        "max": 9999
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "drift",
          "broken",
          "fouled"
        ]
      }
    }
  },
  {
    "type": "gas-analyzer",
    "label": "Gas analyzer",
    "ports": [
      {
        "id": "process",
        "medium": "measurement",
        "direction": "in"
      },
      {
        "id": "signal",
        "medium": "data",
        "direction": "out"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "value": {
        "type": "number",
        "default": 42,
        "min": -9999,
        "max": 9999
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "drift",
          "broken",
          "fouled"
        ]
      }
    }
  },
  {
    "type": "plc-rack",
    "label": "PLC rack",
    "ports": [
      {
        "id": "network",
        "medium": "data",
        "direction": "bidirectional"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "io",
        "medium": "data",
        "direction": "bidirectional"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "connected": {
        "type": "boolean",
        "default": true
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "comms-loss",
          "io-fault",
          "power-loss"
        ]
      }
    }
  },
  {
    "type": "plc-cpu",
    "label": "PLC CPU",
    "ports": [
      {
        "id": "network",
        "medium": "data",
        "direction": "bidirectional"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "backplane",
        "medium": "data",
        "direction": "bidirectional"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "connected": {
        "type": "boolean",
        "default": true
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "comms-loss",
          "io-fault",
          "power-loss"
        ]
      }
    }
  },
  {
    "type": "remote-io",
    "label": "Remote IO station",
    "ports": [
      {
        "id": "network",
        "medium": "data",
        "direction": "bidirectional"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "inputs",
        "medium": "data",
        "direction": "in"
      },
      {
        "id": "outputs",
        "medium": "data",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "connected": {
        "type": "boolean",
        "default": true
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "comms-loss",
          "io-fault",
          "power-loss"
        ]
      }
    }
  },
  {
    "type": "hmi",
    "label": "Operator HMI",
    "ports": [
      {
        "id": "network",
        "medium": "data",
        "direction": "bidirectional"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "connected": {
        "type": "boolean",
        "default": true
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "comms-loss",
          "io-fault",
          "power-loss"
        ]
      }
    }
  },
  {
    "type": "scada-server",
    "label": "SCADA server",
    "ports": [
      {
        "id": "network",
        "medium": "data",
        "direction": "bidirectional"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "connected": {
        "type": "boolean",
        "default": true
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "comms-loss",
          "io-fault",
          "power-loss"
        ]
      }
    }
  },
  {
    "type": "network-switch",
    "label": "Industrial network switch",
    "ports": [
      {
        "id": "uplink",
        "medium": "data",
        "direction": "bidirectional"
      },
      {
        "id": "ports",
        "medium": "data",
        "direction": "bidirectional"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "connected": {
        "type": "boolean",
        "default": true
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "comms-loss",
          "io-fault",
          "power-loss"
        ]
      }
    }
  },
  {
    "type": "radio",
    "label": "Telemetry radio",
    "ports": [
      {
        "id": "network",
        "medium": "data",
        "direction": "bidirectional"
      },
      {
        "id": "power",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "wireless",
        "medium": "data",
        "direction": "bidirectional"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "connected": {
        "type": "boolean",
        "default": true
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "comms-loss",
          "io-fault",
          "power-loss"
        ]
      }
    }
  },
  {
    "type": "pipe",
    "label": "Process pipe",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "open": {
        "type": "boolean",
        "default": true
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "blocked",
          "leaking",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "junction",
    "label": "Four-way junction",
    "ports": [
      {
        "id": "west",
        "medium": "fluid",
        "direction": "bidirectional"
      },
      {
        "id": "east",
        "medium": "fluid",
        "direction": "bidirectional"
      },
      {
        "id": "north",
        "medium": "fluid",
        "direction": "bidirectional"
      },
      {
        "id": "south",
        "medium": "fluid",
        "direction": "bidirectional"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "open": {
        "type": "boolean",
        "default": true
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "blocked",
          "leaking",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "conveyor",
    "label": "Belt conveyor",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "solids",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "crusher",
    "label": "Jaw crusher",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "solids",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "vibrating-screen",
    "label": "Vibrating screen",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "solids",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "grinding-mill",
    "label": "Grinding mill",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "solids",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "rotary-kiln",
    "label": "Rotary kiln",
    "family": "heater",
    "ports": [
      {
        "id": "inlet",
        "medium": "material",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "material",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "fuel",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "air",
        "medium": "air",
        "direction": "in"
      },
      {
        "id": "exhaust",
        "medium": "gas",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 500,
        "min": 0,
        "max": 1800,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "overheated",
          "refractory-damage",
          "fuel-leak"
        ]
      }
    }
  },
  {
    "type": "oven",
    "label": "Industrial oven",
    "family": "heater",
    "ports": [
      {
        "id": "inlet",
        "medium": "material",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "material",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "fuel",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "air",
        "medium": "air",
        "direction": "in"
      },
      {
        "id": "exhaust",
        "medium": "gas",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 180,
        "min": -20,
        "max": 600,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "overheated",
          "refractory-damage",
          "fuel-leak"
        ]
      }
    }
  },
  {
    "type": "dryer",
    "label": "Rotary dryer",
    "family": "heater",
    "ports": [
      {
        "id": "inlet",
        "medium": "material",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "material",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "fuel",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "air",
        "medium": "air",
        "direction": "in"
      },
      {
        "id": "exhaust",
        "medium": "gas",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 90,
        "min": -20,
        "max": 400,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "overheated",
          "refractory-damage",
          "fuel-leak"
        ]
      }
    }
  },
  {
    "type": "extruder",
    "label": "Screw extruder",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "product",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "coolant-in",
        "medium": "thermal-fluid",
        "direction": "in"
      },
      {
        "id": "coolant-out",
        "medium": "thermal-fluid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "tablet-press",
    "label": "Tablet press",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "solids",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "filling-line",
    "label": "Filling line",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "product",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "packaging-line",
    "label": "Packaging line",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "product",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "product",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "granulator",
    "label": "Granulator",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "solids",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "forming-machine",
    "label": "Forming machine",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "product",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "product",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "drum-mixer",
    "label": "Drum mixer",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "solids",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "paper-machine",
    "label": "Paper machine",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "slurry",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "product",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "weigh-hopper",
    "label": "Weigh hopper",
    "family": "storage",
    "ports": [
      {
        "id": "inlet",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "solids",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "ruptured",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "screw-feeder",
    "label": "Screw feeder",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "solids",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "solids",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "centrifuge",
    "label": "Industrial centrifuge",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "reject",
        "medium": "solids",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "flotation-cell",
    "label": "Flotation cell",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "slurry",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "slurry",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "air",
        "medium": "air",
        "direction": "in"
      },
      {
        "id": "reject",
        "medium": "slurry",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "jammed",
          "worn",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "membrane-filter",
    "label": "Membrane filter",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "reject",
        "medium": "liquid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "fouled",
          "leaking",
          "ruptured"
        ]
      }
    }
  },
  {
    "type": "reverse-osmosis",
    "label": "Reverse osmosis skid",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "reject",
        "medium": "liquid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "fouled",
          "leaking",
          "ruptured"
        ]
      }
    }
  },
  {
    "type": "distillation-column",
    "label": "Distillation column",
    "family": "heater",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "vapor",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "heat",
        "medium": "thermal",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 120,
        "min": 0,
        "max": 600,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "fouled",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "separator",
    "label": "Three-phase separator",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "fluid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "fluid",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "gas",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "drain",
        "medium": "liquid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "ruptured",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "cyclone",
    "label": "Cyclone separator",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "solids",
        "medium": "solids",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "blocked",
          "worn",
          "leaking"
        ]
      }
    }
  },
  {
    "type": "scrubber",
    "label": "Wet scrubber",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "wash",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "drain",
        "medium": "liquid",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "fouled",
          "leaking",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "cooling-tower",
    "label": "Cooling tower",
    "family": "heater",
    "ports": [
      {
        "id": "inlet",
        "medium": "thermal-fluid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "thermal-fluid",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "air",
        "medium": "air",
        "direction": "in"
      },
      {
        "id": "vent",
        "medium": "air",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 32,
        "min": -20,
        "max": 100,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "fouled",
          "fan-fault",
          "leaking"
        ]
      }
    }
  },
  {
    "type": "chiller",
    "label": "Industrial chiller",
    "family": "heater",
    "ports": [
      {
        "id": "inlet",
        "medium": "thermal-fluid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "thermal-fluid",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "heat",
        "medium": "thermal",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 7,
        "min": -40,
        "max": 100,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "refrigerant-leak",
          "compressor-fault",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "evaporator",
    "label": "Falling-film evaporator",
    "family": "heater",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "vapor",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "heat",
        "medium": "thermal",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 85,
        "min": -20,
        "max": 400,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "fouled",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "electrolyzer",
    "label": "Water electrolyzer",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "oxygen",
        "medium": "gas",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 65,
        "min": 0,
        "max": 150,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "membrane-damage",
          "leaking",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "fuel-cell",
    "label": "Fuel-cell generator",
    "family": "generator",
    "ports": [
      {
        "id": "inlet",
        "medium": "gas",
        "direction": "in"
      },
      {
        "id": "output",
        "medium": "electricity",
        "direction": "out"
      },
      {
        "id": "water",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "heat",
        "medium": "thermal",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 80,
        "min": 0,
        "max": 1000,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "fuel-starved",
          "stack-damage",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "wellhead",
    "label": "Production wellhead",
    "family": "source",
    "ports": [
      {
        "id": "outlet",
        "medium": "fluid",
        "direction": "out"
      },
      {
        "id": "gas",
        "medium": "gas",
        "direction": "out"
      },
      {
        "id": "control",
        "medium": "data",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "open": {
        "type": "boolean",
        "default": true
      },
      "value": {
        "type": "number",
        "default": 350,
        "min": 0,
        "max": 100000,
        "unit": "kPa"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "blocked",
          "corroded"
        ]
      }
    }
  },
  {
    "type": "wind-turbine",
    "label": "Wind turbine",
    "family": "generator",
    "ports": [
      {
        "id": "output",
        "medium": "electricity",
        "direction": "out"
      },
      {
        "id": "control",
        "medium": "data",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "blade-damage",
          "gearbox-fault",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "aeration-basin",
    "label": "Aeration basin",
    "family": "processor",
    "ports": [
      {
        "id": "inlet",
        "medium": "liquid",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "liquid",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "air",
        "medium": "air",
        "direction": "in"
      },
      {
        "id": "sludge",
        "medium": "sludge",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "level": {
        "type": "number",
        "default": 55,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "leaking",
          "diffuser-fault",
          "foaming"
        ]
      }
    }
  },
  {
    "type": "steam-turbine",
    "label": "Steam turbine",
    "family": "generator",
    "ports": [
      {
        "id": "inlet",
        "medium": "steam",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "steam",
        "direction": "out"
      },
      {
        "id": "output",
        "medium": "electricity",
        "direction": "out"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "temperature": {
        "type": "number",
        "default": 450,
        "min": 0,
        "max": 650,
        "unit": "°C"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "bearing-fault",
          "blade-damage",
          "overheated"
        ]
      }
    }
  },
  {
    "type": "fan",
    "label": "Axial ventilation fan",
    "family": "load",
    "ports": [
      {
        "id": "inlet",
        "medium": "air",
        "direction": "in"
      },
      {
        "id": "outlet",
        "medium": "air",
        "direction": "out"
      },
      {
        "id": "supply",
        "medium": "electricity",
        "direction": "in"
      },
      {
        "id": "control",
        "medium": "data",
        "direction": "in"
      }
    ],
    "visualFields": {
      "active": {
        "type": "boolean",
        "default": true
      },
      "running": {
        "type": "boolean",
        "default": true
      },
      "fault": {
        "type": "boolean",
        "default": false
      },
      "status": {
        "type": "select",
        "default": "normal",
        "options": [
          "normal",
          "warning",
          "offline"
        ]
      },
      "load": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "speed": {
        "type": "number",
        "default": 60,
        "min": 0,
        "max": 100,
        "unit": "%"
      },
      "damage": {
        "type": "select",
        "default": "none",
        "options": [
          "none",
          "blade-damage",
          "seized",
          "overheated"
        ]
      }
    }
  }
];
