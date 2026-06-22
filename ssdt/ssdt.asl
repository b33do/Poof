DefinitionBlock ("ssdt.aml", "SSDT", 2, "OEM", "BATT", 0x00000001)
{
    Device (_SB.ACAD)
    {
        Name (_HID, "ACPI0003")
        Name (_PCL, Package (One) { \_SB })
        Method (_PSR, 0, NotSerialized)
        {
            Return (One)
        }
        Method (_STA, 0, NotSerialized)
        {
            Return (0x0F)
        }
    }

    Device (_SB.BAT0)
    {
        Name (_HID, EISAID ("PNP0C0A"))
        Name (_UID, One)
        Name (_PCL, Package (One) { \_SB })
        Method (_STA, 0, NotSerialized)
        {
            Return (0x1F)
        }

        Method (_BIF, 0, NotSerialized)
        {
            Return (Package (0x0D)
            {
                Zero, 
                0x00002710, 
                0x00002710, 
                One, 
                0x00002E7C, 
                0x000001F4, 
                0x00000064, 
                0x00000064, 
                0x00000064, 
                "Model", 
                "Serial", 
                "Type", 
                "OEM"
            })
        }

        Method (_BST, 0, NotSerialized)
        {
            Return (Package (0x04)
            {
                Zero, 
                Zero, 
                0x00002710, 
                0x00002E7C
            })
        }
    }
}
