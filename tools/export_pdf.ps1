param(
  [Parameter(Mandatory = $true)][string]$Docx,
  [Parameter(Mandatory = $true)][string]$Pdf
)

# 用 Microsoft Word 打开 docx、更新目录页码，再导出 PDF。
# 依赖本机安装的 Word（COM 接口），仅用于生成交付用 PDF，不参与作品运行。
#
# 用法：
#   pwsh -File tools/export_pdf.ps1 -Docx dist\方案.docx -Pdf dist\方案.pdf

$ErrorActionPreference = "Stop"
$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0

try {
    $doc = $word.Documents.Open($Docx, $false, $false)

    foreach ($n in @("TOC 1", "TOC 2", "TOC 3")) {
        try {
            $st = $doc.Styles.Item($n)
            $st.ParagraphFormat.LineSpacingRule = 0
            $st.ParagraphFormat.SpaceBefore = 0
            $st.ParagraphFormat.SpaceAfter = 0
            $st.Font.Size = 10.5
        }
        catch { }
    }

    if ($doc.TablesOfContents.Count -gt 0) { $doc.TablesOfContents.Item(1).Update() }
    $doc.Fields.Update() | Out-Null
    $doc.Repaginate()

    Write-Output ("TOTAL_PAGES=" + $doc.ComputeStatistics(2))
    foreach ($p in $doc.Paragraphs) {
        $s = $p.Style.NameLocal
        if ($s -like "Heading 1*" -or $s -eq "标题 1") {
            Write-Output ("H1`t" + $p.Range.Information(3) + "`t" + $p.Range.Text.Trim())
        }
    }

    $doc.ExportAsFixedFormat($Pdf, 17, $false, 0, 0, 0, 0, 0, $true, $true, 1, $true, $true, $false)
    Write-Output "PDF_SAVED"
    $doc.Close($false)
}
finally {
    $word.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
    [GC]::Collect()
}
