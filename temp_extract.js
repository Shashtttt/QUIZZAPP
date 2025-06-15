
            const fs = require('fs');
            const path = require('path');

            // Load the questions file
            const questionsPath = process.argv[2];
            const questionsContent = fs.readFileSync(questionsPath, 'utf8');

            // Evaluate the content to get questions
            eval(questionsContent);

            // Output questions as JSON
            console.log(JSON.stringify(questions));
            