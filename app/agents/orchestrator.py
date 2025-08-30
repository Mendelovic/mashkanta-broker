"""
Orchestrator agent for the Hebrew mortgage broker AI.

This module contains the main conversational agent that handles mortgage consultations in Hebrew.
"""

import logging
from agents import Agent

from .tools import (
    analyze_document_from_path,
    get_session_documents_status,
    clear_session_documents,
    get_mortgage_advice,
)


logger = logging.getLogger(__name__)


HEBREW_MORTGAGE_BROKER_INSTRUCTIONS = """
אתה יועץ משכנתאות מומחה בשוק הישראלי. אתה מדבר רק עברית ומתמחה בכל היבטי המשכנתאות בישראל.

התפקיד שלך:
1. לספק ייעוץ מקצועי ומדויק במשכנתאות
2. לנתח מסמכים פיננסיים (תלושי שכר, טופס 106, דפי חשבון)
3. לחשב זכאות למשכנתא ולהציע תרחישים
4. להסביר את התהליך בצורה ברורה ומובנה

הכלים העומדים לרשותך:
- ניתוח מסמכים פיננסיים
- חישוב זכאות למשכנתא
- מתן עצות כלליות
- מעקב אחר מסמכים בהפעלה

עקרונות עבודה:
- תמיד דבר בעברית
- היה מקצועי אך ידידותי
- הסבר מונחים פיננסיים בפשטות
- תן המלצות ברורות ומעשיות
- אל תתחייב על הצעות ספציפיות של בנקים
- המלץ תמיד להתייעץ עם בנקים או יועצים נוספים לפני החלטה סופית

תגובות אופייניות:
- הסבר את התהליך שלב אחר שלב
- בקש מסמכים נוספים אם נדרש
- הסבר סיכונים ויתרונות
- תן עצות להשבחת הפרופיל הפיננסי

זכור: אתה כלי עזר לקבלת החלטות, לא חלופה לייעוץ מקצועי אישי.
"""


def create_mortgage_broker_orchestrator() -> Agent:
    """
    Create and configure the main mortgage broker orchestrator agent.

    Returns:
        Configured Agent instance for mortgage consultation in Hebrew
    """
    try:
        agent = Agent(
            name="יועץ משכנתאות ישראלי",
            instructions=HEBREW_MORTGAGE_BROKER_INSTRUCTIONS,
            model="gpt-5-mini",
            tools=[
                analyze_document_from_path,
                get_session_documents_status,
                clear_session_documents,
                get_mortgage_advice,
            ],
        )

        logger.info("Created mortgage broker orchestrator agent successfully")
        return agent

    except Exception as e:
        logger.error(f"Failed to create mortgage broker orchestrator agent: {e}")
        raise


def create_greeting_message() -> str:
    """
    Create a standard Hebrew greeting message for new conversations.

    Returns:
        Hebrew greeting message
    """
    return """שלום! אני היועץ הדיגיטלי שלך למשכנתאות בישראל. 🏠

אני כאן לעזור לך:
• לנתח מסמכים פיננסיים (תלושי שכר, טופס 106, דפי חשבון)
• לחשב זכאות למשכנתא
• להסביר על תהליכי המשכנתא
• לתת עצות כלליות למימון דירה

איך אני יכול לעזור לך היום?

💡 עצה: אם יש לך מסמכים פיננסיים, אתה יכול להעלות אותם ואני אנתח אותם עבורך."""


def create_help_message() -> str:
    """
    Create a help message explaining available features.

    Returns:
        Hebrew help message
    """
    return """עזרה - מה אני יכול לעשות בשבילך:

📋 **ניתוח מסמכים:**
• תלושי שכר - לזיהוי הכנסות חודשיות
• טופס 106 - לאימות הכנסות שנתיות  
• דפי חשבון - לבדיקת דפוסי הכנסה והוצאה

🧮 **חישובי משכנתא:**
• זכאות למשכנתא לפי ההכנסות
• תרחישים שונים (שמרני, סטנדרטי, אגרסיבי)
• הערכת סיכונים

💬 **ייעוץ כללי:**
• הסבר על תהליכי משכנתא
• עצות לשיפור הפרופיל הפיננסי
• המלצות להכנת המסמכים

🔧 **פקודות שימושיות:**
• "מה המצב של המסמכים?" - לבדיקת סטטוס
• "נקה מסמכים" - להתחלה חדשה
• "חשב משכנתא" - לחישוב זכאות

זכור: אני כלי עזר לקבלת החלטות. לייעוץ סופי התייעץ עם מקצועי בבנק או יועץ משכנתאות."""


def create_document_upload_instructions() -> str:
    """
    Create instructions for document upload.

    Returns:
        Hebrew document upload instructions
    """
    return """📄 הוראות העלאת מסמכים:

**מסמכים מומלצים:**
1. **תלושי שכר** - 2-3 חודשים אחרונים
2. **טופס 106** - מהשנה האחרונה
3. **דפי חשבון** - 3 חודשים אחרונים

**דרישות טכניות:**
• פורמט: PDF בלבד
• גודל מקסימלי: 50MB לכל קובץ
• עד 10 קבצים בכל בקשה

**טיפים:**
• ודא שהטקסט ברור וקריא
• כלול מסמכים עדכניים ככל הניתן
• אל תכלול מידע רגיש שאינו נדרש

לאחר העלאת המסמכים, אני אנתח אותם ואציג את התוצאות בעברית."""
