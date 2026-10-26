const satellite = {
    id: 1,
    name: "GoSa",
    orbit: "LEO",
    status: "Active"
};

console.log(satellite);

const fs = require("fs");

const data = fs.readFile("sat.json");
console.log(JSON.parse(data));

const satellites = [
    [
        { "id": 1, "name": "GoSa", "status": "Active" },
        { "id": 2, "name": "MoSa", "status": "Sleep" }
    ],
    [
        { "id": 3, "name": "DoSa", "status": "Active" },
        { "id": 4, "name": "LoSa", "status": "Sleep" }
    ]
];

console.log(satellites);

console.log(satellites[0][0]);
console.log(satellites[1][1].name);
console.log(satellites[0][1].status);