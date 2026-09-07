const fs = require("fs")
const path = require("path")

async function main() {
  const Registry = await ethers.getContractFactory("EvidenceRegistry")
  const registry = await Registry.deploy()
  await registry.waitForDeployment()
  const address = await registry.getAddress()
  const artifact = await artifacts.readArtifact("EvidenceRegistry")
  const output = { contract_address: address, abi: artifact.abi }
  const outputPath = path.join(__dirname, "..", "deployment.json")
  fs.writeFileSync(outputPath, JSON.stringify(output, null, 2))
  console.log(`EvidenceRegistry deployed to: ${address}`)
  console.log(`Deployment details written to: ${outputPath}`)
}

main().catch((error) => { console.error(error); process.exitCode = 1 })
